"""Authenticated loopback HTTP API server and IPC process lifecycle."""

import json
import secrets
import sqlite3
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pydantic

from steadydev.git_collector import (
    collect_git_snapshot,
    collect_review_packet_from_git,
    get_git_status_summary,
    validate_candidate_repo,
    validate_repo_root,
)
from steadydev.models import CheckReceipt, Finding
from steadydev.ollama_client import OllamaClient, OllamaClientError
from steadydev.reviewer import Reviewer
from steadydev.store import SessionStore


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
        store: SessionStore | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.authorized_repo_root = authorized_repo_root.resolve(strict=True)
        self.token = token or secrets.token_urlsafe(32)
        self.ollama_client = ollama_client or OllamaClient()
        self.reviewer = reviewer or Reviewer(ollama_client=self.ollama_client)
        self.store = store or SessionStore(db_path=db_path)
        self._repo_lock = threading.Lock()
        self._is_reviewing = False


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
        elif self.path.startswith("/api/session"):
            repo = self.server.authorized_repo_root
            session = self.server.store.get_or_create_session(str(repo), repo.name)
            findings = self.server.store.get_findings(session["session_id"])
            receipts = self.server.store.get_receipts(session["session_id"])
            session["findings"] = findings
            session["check_receipts"] = receipts
            self.send_json(200, session)
        elif self.path == "/api/repos/recent":
            recents = self.server.store.list_recent_repositories()
            self.send_json(200, {"repositories": recents})
        else:
            self.send_json(
                404, {"error": "not_found", "message": f"Unknown endpoint: {self.path}"}
            )

    def do_PATCH(self) -> None:
        """Handle PATCH endpoints."""
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

        if self.path.startswith("/api/findings/"):
            finding_id = self.path.split("/api/findings/")[-1].strip()
            status = body.get("status")
            user_reason = body.get("user_reason")
            retired_by = body.get("retired_by_receipt_id")
            if not status:
                self.send_json(
                    400, {"error": "bad_request", "message": "Missing 'status' in body"}
                )
                return

            self.server.store.update_finding_status(
                finding_id=finding_id,
                status=status,
                user_reason=user_reason,
                retired_by_receipt_id=retired_by,
            )
            f_updated = self.server.store.get_finding_by_id(finding_id)
            if not f_updated:
                self.send_json(
                    404,
                    {
                        "error": "not_found",
                        "message": f"Finding {finding_id} not found",
                    },
                )
                return
            self.send_json(200, f_updated)
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
            git_status = get_git_status_summary(repo_path, changed, omitted)
            self.send_json(
                200,
                {
                    "repo_name": repo_path.name,
                    "repo_path": str(repo_path),
                    "git_status": git_status,
                    "changed_files": [cf.model_dump() for cf in changed],
                    "omitted_files": omitted,
                    "truncated": truncated,
                },
            )

        elif self.path == "/api/repo/validate":
            target_path_str = body.get("repo_path")
            if not target_path_str:
                self.send_json(
                    400,
                    {"error": "bad_request", "message": "Missing 'repo_path' in body"},
                )
                return

            valid, validated_path, err_msg = validate_candidate_repo(target_path_str)
            if not valid or not validated_path:
                status_code = (
                    403
                    if "forbidden" in (err_msg or "").lower()
                    else 422
                    if "Git" in (err_msg or "")
                    else 400
                )
                self.send_json(
                    status_code,
                    {
                        "error": "invalid_repo",
                        "message": err_msg or "Invalid repository path",
                    },
                )
                return

            git_status = get_git_status_summary(validated_path)
            self.send_json(
                200,
                {
                    "valid": True,
                    "resolved_path": str(validated_path),
                    "repo_name": validated_path.name,
                    "git_status": git_status,
                },
            )

        elif self.path == "/api/repo/select":
            target_path_str = body.get("repo_path")
            if not target_path_str:
                self.send_json(
                    400,
                    {"error": "bad_request", "message": "Missing 'repo_path' in body"},
                )
                return

            if getattr(self.server, "_is_reviewing", False):
                self.send_json(
                    409,
                    {
                        "error": "conflict",
                        "message": "Cannot switch repository while review is in progress",
                    },
                )
                return

            valid, validated_path, err_msg = validate_candidate_repo(target_path_str)
            if not valid or not validated_path:
                status_code = (
                    403
                    if "forbidden" in (err_msg or "").lower()
                    else 422
                    if "Git" in (err_msg or "")
                    else 400
                )
                self.send_json(
                    status_code,
                    {
                        "error": "invalid_repo",
                        "message": err_msg or "Invalid repository path",
                    },
                )
                return

            with self.server._repo_lock:
                self.server.authorized_repo_root = validated_path
                session = self.server.store.get_or_create_session(
                    str(validated_path), validated_path.name
                )
                findings = self.server.store.get_findings(session["session_id"])
                receipts = self.server.store.get_receipts(session["session_id"])
                session["findings"] = findings
                session["check_receipts"] = receipts
                session["git_status"] = get_git_status_summary(validated_path)

            self.send_json(200, session)

        elif self.path == "/api/session":
            repo_path = self._validate_requested_repo(body.get("repo_path"))
            if not repo_path:
                return
            session = self.server.store.get_or_create_session(
                str(repo_path), repo_path.name
            )
            intention = body.get("intention")
            criteria = body.get("criteria")
            if intention is not None and criteria is not None:
                self.server.store.update_session_intention(
                    session["session_id"], intention, criteria
                )
            updated = self.server.store.get_session_by_id(session["session_id"])
            self.send_json(200, updated or {})

        elif self.path == "/api/session/note":
            repo_path = self._validate_requested_repo(body.get("repo_path"))
            if not repo_path:
                return
            session = self.server.store.get_or_create_session(
                str(repo_path), repo_path.name
            )
            note_text = body.get("restart_note", "")
            is_edited = body.get("is_user_edited", True)
            self.server.store.save_restart_note(
                session["session_id"], note_text, is_edited
            )
            updated = self.server.store.get_session_by_id(session["session_id"])
            self.send_json(200, updated or {})

        elif self.path == "/api/session/close":
            repo_path = self._validate_requested_repo(body.get("repo_path"))
            if not repo_path:
                return
            session = self.server.store.get_or_create_session(
                str(repo_path), repo_path.name
            )
            closing_summary = body.get("closing_summary")
            self.server.store.close_session(session["session_id"], closing_summary)
            updated = self.server.store.get_session_by_id(session["session_id"])
            self.send_json(200, updated or {})

        elif self.path in ("/api/session/reset", "/api/session/new"):
            repo_path = self._validate_requested_repo(body.get("repo_path"))
            if not repo_path:
                return
            intention = body.get("intention", "Review current session changes")
            criteria = body.get("criteria", [])
            fresh_session = self.server.store.reset_session(
                str(repo_path),
                repo_path.name,
                intention=intention,
                criteria=criteria,
            )
            findings = self.server.store.get_findings(fresh_session["session_id"])
            receipts = self.server.store.get_receipts(fresh_session["session_id"])
            git_summary = get_git_status_summary(repo_path)
            fresh_session["findings"] = findings
            fresh_session["check_receipts"] = receipts
            fresh_session["git_status"] = git_summary
            self.send_json(200, fresh_session)

        elif self.path == "/api/review":
            repo_path = self._validate_requested_repo(body.get("repo_path"))
            if not repo_path:
                return

            self.server._is_reviewing = True
            try:
                session = self.server.store.get_or_create_session(
                    str(repo_path), repo_path.name
                )
                intention = body.get("session_intention") or session.get(
                    "intention", "Review current session changes"
                )
                criteria = body.get("acceptance_criteria") or session.get(
                    "criteria", []
                )
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

                # Check snapshot conflict if expected_snapshot_hash provided
                expected_hash = body.get("expected_snapshot_hash")
                if expected_hash and expected_hash != packet.snapshot_hash:
                    self.send_json(
                        409,
                        {
                            "error": "conflict",
                            "message": f"Snapshot mismatch: working tree changed (current={packet.snapshot_hash}, expected={expected_hash})",
                            "current_snapshot_hash": packet.snapshot_hash,
                        },
                    )
                    return

                model_name = body.get("model", "gemma3:4b")
                fallback_model = body.get("fallback_model", "qwen2.5-coder:3b")
                result = self.server.reviewer.review(
                    packet,
                    model_name=model_name,
                    fallback_model_name=fallback_model,
                )

                # Persist snapshot, receipts, and findings to SQLite store
                head_sha = packet.git_head_sha or "0" * 40
                snap_id = self.server.store.save_snapshot(
                    session_id=session["session_id"],
                    git_head_sha=head_sha,
                    diff_hash="",
                    untracked_hash="",
                    composite_hash=packet.snapshot_hash or "",
                )
                self.server.store.save_receipts(
                    session["session_id"], snap_id, receipts
                )
                self.server.store.save_findings(
                    session["session_id"], snap_id, result.findings
                )

                if result.retired_finding_ids:
                    for rid in result.retired_finding_ids:
                        self.server.store.update_finding_status(rid, "evidence-retired")

                # Update restart note only if user has not edited it
                if session.get("is_note_user_edited", 0) == 0 and result.restart_note:
                    self.server.store.save_restart_note(
                        session["session_id"], result.restart_note, is_user_edited=False
                    )
                else:
                    # Keep user-edited restart note in response
                    result.restart_note = session.get(
                        "restart_note", result.restart_note
                    )

                self.send_json(200, result.model_dump(mode="json"))
            finally:
                self.server._is_reviewing = False

        elif self.path == "/api/shutdown":
            self.send_json(200, {"status": "shutting_down"})
            try:
                self.server.store.checkpoint(mode="TRUNCATE")
            except (sqlite3.Error, OSError) as exc:
                sys.stderr.write(f"Shutdown checkpoint warning: {exc}\n")
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
    store: SessionStore | None = None,
    db_path: Path | str | None = None,
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
        store=store,
        db_path=db_path,
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
    parser.add_argument(
        "--db-path", default=None, help="Custom SQLite database path (optional)"
    )
    args = parser.parse_args()

    start_stdin_watchdog()
    server = create_server(
        args.repo_path, port=args.port, token=args.token, db_path=args.db_path
    )
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
