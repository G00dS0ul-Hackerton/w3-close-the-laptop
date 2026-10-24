"""Unit tests for OllamaClient using httpx MockTransport."""

import httpx
import pytest

from steadydev.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
)


def test_get_version_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"version": "0.40.6"})

    client = OllamaClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.get_version() == "0.40.6"


def test_get_version_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    client = OllamaClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(OllamaConnectionError):
        client.get_version()


def test_chat_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5-coder:3b",
                "message": {"role": "assistant", "content": '{"status": "clean"}'},
                "total_duration": 5000000000,
                "load_duration": 1000000000,
                "prompt_eval_duration": 2000000000,
                "eval_duration": 2000000000,
                "eval_count": 20,
            },
        )

    client = OllamaClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = client.chat("qwen2.5-coder:3b", [{"role": "user", "content": "hi"}])
    assert result["content"] == '{"status": "clean"}'
    assert result["total_duration_ms"] == 5000.0
    assert result["load_duration_ms"] == 1000.0
    assert result["eval_count"] == 20


def test_chat_model_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model 'ghost' not found"})

    client = OllamaClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(OllamaModelNotFoundError):
        client.chat("ghost", [{"role": "user", "content": "hi"}])


def test_chat_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Read timed out")

    client = OllamaClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(OllamaTimeoutError):
        client.chat("gemma3:4b", [{"role": "user", "content": "hi"}])


def test_unload_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"done": True, "done_reason": "unload"})

    client = OllamaClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.unload_model("gemma3:4b") is True


def test_chat_default_cpu_options() -> None:
    captured_payload = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        import json

        captured_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5-coder:3b",
                "message": {"role": "assistant", "content": "{}"},
                "total_duration": 1000000,
            },
        )

    client = OllamaClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    client.chat("qwen2.5-coder:3b", [{"role": "user", "content": "hi"}])
    opts = captured_payload.get("options", {})
    assert opts.get("num_ctx") == 4096
    assert opts.get("num_predict") == 1024
    assert "num_thread" in opts
    assert opts.get("repeat_penalty") == 1.1
