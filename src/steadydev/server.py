"""Authenticated loopback HTTP API server and IPC process lifecycle."""

import json
import secrets
import sqlite3
import sys
import threading
import uuid
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


class ReviewJob:
    """Encapsulates job authority and cancellation predicate for a review."""

    def __init__(self, job_id: str, repo_path: str, session_id: str) -> None:
        self.job_id = job_id
        self.repo_path = repo_path
        self.session_id = session_id
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()


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
        self._job_lock = threading.Lock()
        self._active_job: ReviewJob | None = None
        self._is_reviewing = False
        self._review_lock = threading.Lock()
        self._review_progress: dict[str, Any] = {
            "is_reviewing": False,
            "current_chunk": 0,
            "total_chunks": 0,
            "current_files": "",
            "phase": "idle",
        }

    def update_review_progress(
        self, current: int, total: int, files: str, phase: str = "auditing"
    ) -> None:
        with self._review_lock:
            self._review_progress = {
                "is_reviewing": True,
                "current_chunk": current,
                "total_chunks": total,
                "current_files": files,
                "phase": phase,
            }

    def reset_review_progress(self) -> None:
        with self._review_lock:
            self._review_progress = {
                "is_reviewing": False,
                "current_chunk": 0,
                "total_chunks": 0,
                "current_files": "",
                "phase": "idle",
            }


def format_model_display_name(
    model_name: str, details: dict[str, Any] | None = None
) -> str:
    """Format an Ollama model name like 'gemma3:4b' into 'Gemma 3 (4B)'."""
    if not model_name:
        return "Unknown"
    if model_name in ("baseline", "baseline-checklist"):
        return "Baseline Checklist (Offline Floor)"

    parts = model_name.split(":", 1)
    base = parts[0]
    tag = parts[1] if len(parts) > 1 else ""

    if base.startswith("gemma"):
        version = base[5:]
        base_str = f"Gemma {version}".strip()
    elif base.startswith("qwen") and "coder" in base:
        sub = base.replace("qwen", "").replace("-coder", "").strip()
        base_str = f"Qwen {sub} Coder".strip()
    elif base.startswith("qwen"):
        sub = base.replace("qwen", "").strip()
        base_str = f"Qwen {sub}".strip()
    else:
        base_str = base.replace("-", " ").title()

    param_size = (
        tag.upper() if tag else (details.get("parameter_size") if details else "")
    )
    if param_size:
        return f"{base_str} ({param_size})"
    return base_str


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
                    "active_model": "gemma3:4b",
                    "running_models": running,
                },
            )
        elif self.path == "/api/models":
            ollama_ready = False
            raw_models: list[dict[str, Any]] = []
            running_names: set[str] = set()
            try:
                raw_models = self.server.ollama_client.list_models()
                running = self.server.ollama_client.get_running_models()
                running_names = {r.get("name", "") for r in running}
                ollama_ready = True
            except (OllamaClientError, OSError):
                raw_models = []
                running_names = set()

            enriched_models: list[dict[str, Any]] = []
            for m in raw_models:
                m_name = m.get("name", "")
                if not m_name:
                    continue
                details = m.get("details") or {}
                param_size = str(details.get("parameter_size") or "")
                family = str(details.get("family") or "")
                quant = str(details.get("quantization_level") or "")
                size_b = m.get("size") or 0
                is_running = m_name in running_names
                is_rec = m_name.startswith("gemma3:4b")

                enriched_models.append(
                    {
                        "id": m_name,
                        "name": m_name,
                        "display_name": format_model_display_name(m_name, details),
                        "family": family,
                        "parameter_size": param_size,
                        "quantization": quant,
                        "size_bytes": size_b,
                        "is_running": is_running,
                        "is_recommended": is_rec,
                        "is_baseline": False,
                    }
                )

            # Baseline checklist floor is always available
            enriched_models.append(
                {
                    "id": "baseline-checklist",
                    "name": "baseline-checklist",
                    "display_name": "Baseline Checklist (Offline Floor)",
                    "family": "deterministic",
                    "parameter_size": "0B",
                    "quantization": "N/A",
                    "size_bytes": 0,
                    "is_running": True,
                    "is_recommended": False,
                    "is_baseline": True,
                }
            )

            self.send_json(
                200,
                {
                    "status": "ok",
                    "ollama_status": "ready" if ollama_ready else "unavailable",
                    "default_model": "gemma3:4b"
                    if ollama_ready
                    else "baseline-checklist",
                    "models": enriched_models,
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
        elif self.path == "/api/review/progress":
            with self.server._review_lock:
                progress_copy = dict(self.server._review_progress)
            self.send_json(200, progress_copy)
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

            repo = self.server.authorized_repo_root
            session = self.server.store.get_or_create_session(str(repo), repo.name)
            self.server.store.update_finding_status(
                finding_id=finding_id,
                status=status,
                user_reason=user_reason,
                retired_by_receipt_id=retired_by,
                session_id=session["session_id"],
            )
            f_updated = self.server.store.get_finding_by_id(
                finding_id, session_id=session["session_id"]
            )
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
            with self.server._job_lock:
                if self.server._active_job is not None:
                    self.server._active_job.cancel()
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
            with self.server._job_lock:
                if self.server._active_job is not None:
                    self.server._active_job.cancel()
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

            with self.server._job_lock:
                if self.server._active_job is not None:
                    self.send_json(
                        409,
                        {
                            "error": "conflict",
                            "message": "Review already in progress",
                        },
                    )
                    return
                session = self.server.store.get_or_create_session(
                    str(repo_path), repo_path.name
                )
                job = ReviewJob(
                    job_id=f"job-{uuid.uuid4().hex[:8]}",
                    repo_path=str(repo_path),
                    session_id=session["session_id"],
                )
                self.server._active_job = job
                self.server._is_reviewing = True

            def on_progress(cur: int, tot: int, files: str) -> None:
                if job.is_cancelled():
                    return
                phase = "synthesizing" if "Synthesizing" in files else "auditing"
                self.server.update_review_progress(cur, tot, files, phase=phase)

            self.server.update_review_progress(
                0, 1, "Starting snapshot review...", phase="starting"
            )
            try:
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

                if job.is_cancelled():
                    self.send_json(
                        409,
                        {
                            "error": "conflict",
                            "message": "Review was cancelled before inference",
                            "status": "cancelled",
                        },
                    )
                    return

                model_name = body.get("model", "gemma3:4b")
                fallback_model = body.get("fallback_model", "qwen2.5-coder:3b")
                workflow_timeout = body.get("workflow_timeout_seconds", 180.0)
                result = self.server.reviewer.review(
                    packet,
                    model_name=model_name,
                    fallback_model_name=fallback_model,
                    progress_callback=on_progress,
                    is_cancelled=job.is_cancelled,
                    workflow_timeout_seconds=workflow_timeout,
                )

                if job.is_cancelled() or result.status == "cancelled":
                    self.send_json(
                        409,
                        {
                            "error": "conflict",
                            "message": "Review was cancelled; results discarded",
                            "status": "cancelled",
                        },
                    )
                    return

                # Re-verify session in database before publishing
                current_sess = self.server.store.get_or_create_session(
                    str(repo_path), repo_path.name
                )
                if (
                    current_sess["session_id"] != session["session_id"]
                    or current_sess.get("status") == "finalized"
                ):
                    self.send_json(
                        409,
                        {
                            "error": "conflict",
                            "message": "Session was reset or closed during review; results discarded",
                            "status": "cancelled",
                        },
                    )
                    return

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
                        self.server.store.update_finding_status(
                            finding_id=rid,
                            status="evidence-retired",
                            session_id=session["session_id"],
                        )

                # Update restart note only if user has not edited it in the database
                fresh_note_sess = self.server.store.get_or_create_session(
                    str(repo_path), repo_path.name
                )
                if (
                    fresh_note_sess.get("is_note_user_edited", 0) == 0
                    and result.restart_note
                ):
                    self.server.store.save_restart_note(
                        session["session_id"], result.restart_note, is_user_edited=False
                    )
                else:
                    result.restart_note = fresh_note_sess.get(
                        "restart_note", result.restart_note
                    )

                self.send_json(200, result.model_dump(mode="json"))
            finally:
                with self.server._job_lock:
                    if self.server._active_job is job:
                        self.server._active_job = None
                        self.server._is_reviewing = False
                        self.server.reset_review_progress()

        elif self.path == "/api/review/cancel":
            with self.server._job_lock:
                if hasattr(self.server.reviewer, "cancel_active"):
                    self.server.reviewer.cancel_active()
                if self.server._active_job is not None:
                    self.server._active_job.cancel()
                    self.server.reset_review_progress()
                    self.send_json(
                        200, {"status": "cancelled", "message": "Review cancelled"}
                    )
                else:
                    self.server.reset_review_progress()
                    self.send_json(
                        200, {"status": "cancelled", "message": "No review in progress"}
                    )

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
