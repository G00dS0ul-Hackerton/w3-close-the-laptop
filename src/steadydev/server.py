"""Authenticated loopback HTTP API server and IPC process lifecycle."""

import json
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pydantic

from steadydev.git_collector import (
    collect_git_snapshot,
    collect_review_packet_from_git,
    validate_repo_root,
)
from steadydev.models import CheckReceipt, Finding
from steadydev.ollama_client import OllamaClient, OllamaClientError
from steadydev.reviewer import Reviewer


class SteadyDevServer(ThreadingHTTPServer):
    """Threaded loopback server bound to 127.0.0.1 with per-launch token auth."""

    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass: type[BaseHTTPRequestHandler],
        authorized_repo_root: Path,
        token: str | None = None,
        ollama_client: OllamaClient | None = None,
        reviewer: Reviewer | None = None,
    ) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.authorized_repo_root = authorized_repo_root.resolve(strict=True)
        self.token = token or secrets.token_urlsafe(32)
        self.ollama_client = ollama_client or OllamaClient()
        self.reviewer = reviewer or Reviewer(ollama_client=self.ollama_client)


class SteadyDevHandler(BaseHTTPRequestHandler):
    """Request handler enforcing token auth, repo boundaries, and clean error codes."""

    server: SteadyDevServer

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP access logs to prevent token/path leakage."""

    def _check_auth(self) -> bool:
        """Verify Authorization: Bearer <token> in constant time."""
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            self.send_json(
                401,
                {
                    "error": "unauthorized",
                    "message": "Missing or malformed bearer token",
                },
            )
            return False

        token_candidate = auth_header[7:].strip()
        if not secrets.compare_digest(token_candidate, self.server.token):
            self.send_json(
                401, {"error": "unauthorized", "message": "Invalid authorization token"}
            )
            return False

        return True

    def _validate_requested_repo(self, repo_path_str: str | None) -> Path | None:
        """Verify requested repo resolves strictly inside the authorized repository root."""
        if not repo_path_str or repo_path_str in (
            ".",
            "",
            self.server.authorized_repo_root.name,
            "sample-project",
        ):
            return self.server.authorized_repo_root

        try:
            candidate = Path(repo_path_str).resolve()
            if not candidate.is_relative_to(self.server.authorized_repo_root):
                self.send_json(
                    403,
                    {
                        "error": "forbidden",
                        "message": f"Requested repository '{repo_path_str}' is outside authorized boundary",
                    },
                )
                return None
            if (
                not (candidate / ".git").exists()
                and candidate != self.server.authorized_repo_root
            ):
                self.send_json(
                    403,
                    {
                        "error": "forbidden",
                        "message": f"Path '{repo_path_str}' is not a valid git repository",
                    },
                )
                return None
            return candidate
        except (OSError, ValueError):
            self.send_json(
                403,
                {"error": "forbidden", "message": "Invalid path specified"},
            )
            return None

    def send_json(self, status: int, data: dict[str, Any]) -> None:
        """Send clean JSON response with UTF-8 encoding."""
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        """Handle GET endpoints."""
        if not self._check_auth():
            return

        if self.path == "/api/health":
            # Check Ollama reachability
            ollama_ready = False
            try:
                running = self.server.ollama_client.get_running_models()
                ollama_ready = True
            except (OllamaClientError, OSError):
                running = []

            self.send_json(
                200,
                {
                    "status": "ok",
                    "version": "0.1.0",
                    "model_status": "ready" if ollama_ready else "unavailable",
                    "active_model": "qwen2.5-coder:3b",
                    "running_models": running,
                },
            )
        else:
            self.send_json(
                404, {"error": "not_found", "message": f"Unknown endpoint: {self.path}"}
            )

    def do_POST(self) -> None:
        """Handle POST endpoints."""
        if not self._check_auth():
            return

        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length > 0 else b"{}"

        try:
            body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except json.JSONDecodeError:
            self.send_json(
                400, {"error": "bad_request", "message": "Invalid JSON body"}
            )
            return

        if self.path == "/api/snapshot":
            repo_path = self._validate_requested_repo(body.get("repo_path"))
            if not repo_path:
                return

            changed, omitted, truncated = collect_git_snapshot(repo_path)
            self.send_json(
                200,
                {
                    "repo_name": repo_path.name,
                    "changed_files": [cf.model_dump() for cf in changed],
                    "omitted_files": omitted,
                    "truncated": truncated,
                },
            )

        elif self.path == "/api/review":
            repo_path = self._validate_requested_repo(body.get("repo_path"))
            if not repo_path:
                return

            intention = body.get("session_intention", "Review current session changes")
            criteria = body.get("acceptance_criteria", [])
            receipts_raw = body.get("check_receipts", [])
            prior_raw = body.get("prior_findings", [])
            deferrals = body.get("explicit_deferrals", [])

            try:
                receipts = [CheckReceipt(**r) for r in receipts_raw]
                prior = [Finding(**f) for f in prior_raw]
            except (pydantic.ValidationError, TypeError, ValueError) as exc:
                self.send_json(
                    400,
                    {
                        "error": "bad_request",
                        "message": f"Invalid model payload schema: {exc}",
                    },
                )
                return

            packet = collect_review_packet_from_git(
                repo_path=repo_path,
                session_intention=intention,
                acceptance_criteria=criteria,
                check_receipts=receipts,
                prior_findings=prior,
                explicit_deferrals=deferrals,
            )

            model_name = body.get("model", "qwen2.5-coder:3b")
            result = self.server.reviewer.review(packet, model_name=model_name)
            self.send_json(200, result.model_dump(mode="json"))

        elif self.path == "/api/shutdown":
            self.send_json(200, {"status": "shutting_down"})
            # Shutdown server in background thread so response finishes
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        else:
            self.send_json(
                404, {"error": "not_found", "message": f"Unknown endpoint: {self.path}"}
            )


def create_server(
    repo_root: str | Path,
    port: int = 0,
    token: str | None = None,
    ollama_client: OllamaClient | None = None,
    reviewer: Reviewer | None = None,
) -> SteadyDevServer:
    """Create and bind a SteadyDevServer instance on loopback 127.0.0.1."""
    root_path = validate_repo_root(repo_root)
    server = SteadyDevServer(
        ("127.0.0.1", port),
        SteadyDevHandler,
        authorized_repo_root=root_path,
        token=token,
        ollama_client=ollama_client,
        reviewer=reviewer,
    )
    return server


def start_stdin_watchdog() -> None:
    """Start background daemon thread that terminates the process on parent stdin close."""

    def _watch():
        try:
            sys.stdin.buffer.read(1)
        except (OSError, ValueError):
            pass
        import os

        os._exit(0)

    t = threading.Thread(target=_watch, daemon=True, name="stdin_watchdog")
    t.start()


def main() -> None:
    """CLI entrypoint for running the SteadyDev loopback engine."""
    import argparse

    parser = argparse.ArgumentParser(description="SteadyDev Loopback Engine")
    parser.add_argument(
        "--repo-path", required=True, help="Path to authorized repository root"
    )
    parser.add_argument(
        "--port", type=int, default=0, help="Port to bind (default: 0 for dynamic)"
    )
    parser.add_argument(
        "--token", default=None, help="Pre-shared auth token (optional)"
    )
    args = parser.parse_args()

    start_stdin_watchdog()
    server = create_server(args.repo_path, port=args.port, token=args.token)
    bound_port = server.server_port
    token = server.token

    # Emit handshake line to stdout and flush immediately
    sys.stdout.write(f"STEADYDEV_READY port={bound_port} token={token}\n")
    sys.stdout.flush()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
