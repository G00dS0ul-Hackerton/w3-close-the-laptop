"""Local Ollama HTTP client adapter with strict timeouts and error mappings."""

import contextlib
import os
import threading
from typing import Any

import httpx


class OllamaClientError(Exception):
    """Base exception for Ollama client interactions."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class OllamaConnectionError(OllamaClientError):
    """Raised when Ollama daemon is unreachable."""


class OllamaTimeoutError(OllamaClientError):
    """Raised when an inference call times out."""


class OllamaModelNotFoundError(OllamaClientError):
    """Raised when the requested model is not pulled."""


class OllamaResponseError(OllamaClientError):
    """Raised when Ollama returns an HTTP error code (clean mapping per C-1)."""


class OllamaClient:
    """HTTP client wrapper for Ollama daemon on loopback."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        connect_timeout: float = 10.0,
        read_timeout: float | None = None,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=15.0,
            pool=10.0,
        )
        self._client_lock = threading.Lock()
        self._client = client or httpx.Client(
            base_url=self.base_url, timeout=self.timeout
        )

    def get_version(self) -> str:
        """Query Ollama daemon version."""
        try:
            resp = self._client.get(f"{self.base_url}/api/version")
            resp.raise_for_status()
            return str(resp.json().get("version", ""))
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Ollama daemon unreachable at {self.base_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Ollama version check timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaResponseError(
                f"Ollama version query failed with HTTP {exc.response.status_code}",
                status_code=exc.response.status_code,
            ) from exc

    def list_models(self) -> list[dict[str, Any]]:
        """List all locally available model tags."""
        try:
            resp = self._client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            return resp.json().get("models", [])
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Ollama daemon unreachable at {self.base_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Ollama tags query timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaResponseError(
                f"Ollama tags query failed with HTTP {exc.response.status_code}",
                status_code=exc.response.status_code,
            ) from exc

    def get_running_models(self) -> list[dict[str, Any]]:
        """List currently resident in-memory models."""
        try:
            resp = self._client.get(f"{self.base_url}/api/ps")
            resp.raise_for_status()
            return resp.json().get("models", [])
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Ollama daemon unreachable at {self.base_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Ollama ps query timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaResponseError(
                f"Ollama ps query failed with HTTP {exc.response.status_code}",
                status_code=exc.response.status_code,
            ) from exc

    def unload_model(self, model_name: str) -> bool:
        """Immediately unload a model from RAM via keep_alive: 0."""
        payload = {"model": model_name, "keep_alive": 0}
        try:
            resp = self._client.post(f"{self.base_url}/api/generate", json=payload)
            return resp.status_code in (200, 404)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
            return False

    def cancel_active(self, active_model: str | None = None) -> None:
        """Sever active HTTP socket connection and unload model from memory."""
        with self._client_lock:
            with contextlib.suppress(httpx.HTTPError, OSError):
                self._client.close()
            self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)
        if active_model:
            self.unload_model(active_model)

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        json_format: bool = True,
        keep_alive: str = "5m",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute a chat completion with structured output and CPU timing capture."""
        opts = {
            "temperature": 0.0,
            "num_ctx": 4096,
            "num_predict": 1024,
            "num_thread": max(1, (os.cpu_count() or 4) // 2),
            "repeat_penalty": 1.1,
            "seed": 42,
        }
        if options:
            opts.update(options)

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": opts,
            "keep_alive": keep_alive,
        }
        if json_format:
            payload["format"] = "json"

        try:
            post_kwargs: dict[str, Any] = {"json": payload}
            if timeout is not None:
                post_kwargs["timeout"] = timeout
            resp = self._client.post(f"{self.base_url}/api/chat", **post_kwargs)

            if resp.status_code == 404:
                raise OllamaModelNotFoundError(
                    f"Model '{model}' not found in Ollama catalog", status_code=404
                )

            resp.raise_for_status()
            data = resp.json()

            # Extract timings (nanoseconds converted to milliseconds)
            total_ms = data.get("total_duration", 0) / 1_000_000.0
            load_ms = data.get("load_duration", 0) / 1_000_000.0
            prompt_eval_ms = data.get("prompt_eval_duration", 0) / 1_000_000.0
            eval_ms = data.get("eval_duration", 0) / 1_000_000.0

            content = data.get("message", {}).get("content", "")

            return {
                "content": content,
                "model": data.get("model", model),
                "done_reason": data.get("done_reason", "stop"),
                "total_duration_ms": total_ms,
                "load_duration_ms": load_ms,
                "prompt_eval_duration_ms": prompt_eval_ms,
                "eval_duration_ms": eval_ms,
                "eval_count": data.get("eval_count", 0),
                "prompt_eval_count": data.get("prompt_eval_count", 0),
            }

        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Ollama daemon unreachable at {self.base_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            timeout_desc = (
                f"{timeout}s"
                if timeout is not None
                else (
                    f"{self.timeout.read}s"
                    if self.timeout.read is not None
                    else "unlimited read timeout"
                )
            )
            raise OllamaTimeoutError(
                f"Inference request for model '{model}' timed out after {timeout_desc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaResponseError(
                f"Inference request failed with HTTP {exc.response.status_code}",
                status_code=exc.response.status_code,
            ) from exc
        except (httpx.RequestError, RuntimeError, OSError) as exc:
            raise OllamaClientError(
                f"Inference request aborted or socket closed: {exc}"
            ) from exc
