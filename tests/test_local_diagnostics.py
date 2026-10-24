"""Tests for local review diagnostics loopback endpoint and lifecycle tracking."""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from steadydev.models import (
    ChunkProvenance,
    ModelAttempt,
    ReviewPacket,
    ReviewResult,
)
from steadydev.server import create_server


class MockDiagnosticReviewer:
    """Mock reviewer returning detailed chunk provenance and attempt telemetry."""

    def review(
        self,
        packet: ReviewPacket,
        model_name: str | None = None,
        progress_callback: Any = None,
        is_cancelled: Any = None,
        workflow_timeout_seconds: float = 180.0,
        **kwargs: Any,
    ) -> ReviewResult:
        if progress_callback:
            progress_callback(1, 1, "test_file.py")

        attempts = [
            ModelAttempt(
                model=model_name or "gemma3:4b",
                outcome="success",
                duration_ms=450.0,
                input_tokens=120,
                output_tokens=30,
                done_reason="stop",
            )
        ]
        provenance = [
            ChunkProvenance(
                chunk_index=1,
                total_chunks=1,
                file_paths=[f.path for f in packet.changed_files] or ["test_file.py"],
                attempts=attempts,
                resolved_engine=model_name or "gemma3:4b",
                findings_count=0,
            )
        ]

        return ReviewResult(
            packet_id=packet.packet_id,
            model_name=model_name or "gemma3:4b",
            status="clean",
            findings=[],
            retired_finding_ids=[],
            closing_summary="Diagnostics mock summary.",
            restart_note="Diagnostics mock restart note.",
            timing_ms={"total_duration_ms": 450.0},
            chunk_provenance=provenance,
        )


@pytest.fixture
def running_diagnostic_server(temp_git_repo: Path):
    """Start SteadyDevServer on ephemeral port with MockDiagnosticReviewer."""
    server = create_server(
        repo_root=temp_git_repo,
        port=0,
        token="test-diag-token-999",
        reviewer=MockDiagnosticReviewer(),  # type: ignore
        db_path=temp_git_repo.parent / "diag_test.db",
    )
    port = server.server_port
    token = server.token

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.05)

    base_url = f"http://127.0.0.1:{port}"
    try:
        yield {
            "base_url": base_url,
            "token": token,
            "repo_root": temp_git_repo,
            "server": server,
        }
    finally:
        server.shutdown()
        server.server_close()


def test_diagnostics_initial_state(running_diagnostic_server):
    """GET /api/review/diagnostics returns idle initial lifecycle state."""
    base = running_diagnostic_server["base_url"]
    tok = running_diagnostic_server["token"]
    headers = {"Authorization": f"Bearer {tok}"}

    resp = httpx.get(f"{base}/api/review/diagnostics", headers=headers, timeout=5.0)
    assert resp.status_code == 200
    data = resp.json()

    assert data["phase"] == "idle"
    assert data["is_reviewing"] is False
    assert data["total_chunks"] == 0
    assert data["chunk_diagnostics"] == []
    assert data["deadline_seconds"] == 180.0


def test_diagnostics_lifecycle_after_review(running_diagnostic_server):
    """Executing review transitions lifecycle to completed and populates attempts."""
    base = running_diagnostic_server["base_url"]
    tok = running_diagnostic_server["token"]
    repo = running_diagnostic_server["repo_root"]
    headers = {"Authorization": f"Bearer {tok}"}

    # Trigger review
    body = {
        "repo_path": str(repo),
        "session_intention": "Test diagnostics endpoint",
        "acceptance_criteria": ["All diagnostics valid"],
        "model": "gemma3:4b",
    }
    rev_resp = httpx.post(
        f"{base}/api/review", json=body, headers=headers, timeout=10.0
    )
    assert rev_resp.status_code == 200

    # Query diagnostics
    diag_resp = httpx.get(
        f"{base}/api/review/diagnostics", headers=headers, timeout=5.0
    )
    assert diag_resp.status_code == 200
    diag = diag_resp.json()

    assert diag["phase"] == "completed"
    assert diag["is_reviewing"] is False
    assert diag["status"] == "clean"
    assert diag["elapsed_ms"] == 450.0
    assert len(diag["chunk_diagnostics"]) == 1

    chunk = diag["chunk_diagnostics"][0]
    assert chunk["chunk_index"] == 1
    assert chunk["resolved_engine"] == "gemma3:4b"
    assert len(chunk["attempts"]) == 1

    attempt = chunk["attempts"][0]
    assert attempt["model"] == "gemma3:4b"
    assert attempt["outcome"] == "success"
    assert attempt["duration_ms"] == 450.0
    assert attempt["input_tokens"] == 120
    assert attempt["output_tokens"] == 30
    assert attempt["done_reason"] == "stop"


def test_diagnostics_privacy_sanitization(running_diagnostic_server):
    """Diagnostics payload contains zero raw code, diffs, prompts, or personal paths."""
    base = running_diagnostic_server["base_url"]
    tok = running_diagnostic_server["token"]
    repo = running_diagnostic_server["repo_root"]
    headers = {"Authorization": f"Bearer {tok}"}

    body = {
        "repo_path": str(repo),
        "session_intention": "Check privacy scrub",
        "model": "gemma3:4b",
    }
    httpx.post(f"{base}/api/review", json=body, headers=headers, timeout=10.0)

    diag_resp = httpx.get(
        f"{base}/api/review/diagnostics", headers=headers, timeout=5.0
    )
    diag_text = json.dumps(diag_resp.json())

    # Assert no code keywords or diff headers
    assert "diff --git" not in diag_text
    assert "@@ -" not in diag_text
    assert "Review this session context chunk" not in diag_text

    # Assert no Windows absolute user paths or secrets
    userprofile = os.environ.get("USERPROFILE", "")
    username = os.path.basename(userprofile) if userprofile else ""
    if username and len(username) > 3:
        # Check that full raw user path is not exposed
        assert userprofile.replace("\\", "\\\\") not in diag_text


def test_diagnostics_offline_core(running_diagnostic_server, monkeypatch):
    """Diagnostics works 100% offline with zero Sentry configuration."""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.setenv("STEADYDEV_SENTRY_ENABLED", "0")

    base = running_diagnostic_server["base_url"]
    tok = running_diagnostic_server["token"]
    headers = {"Authorization": f"Bearer {tok}"}

    resp = httpx.get(f"{base}/api/review/diagnostics", headers=headers, timeout=5.0)
    assert resp.status_code == 200
    assert resp.json()["phase"] in ("idle", "completed")


def test_complete_lifecycle_marks_completed_despite_informational_error(
    running_diagnostic_server,
):
    """Informational error notice on successful review must NOT mark lifecycle phase as 'failed'."""
    server = running_diagnostic_server["server"]
    server.start_lifecycle(
        review_id="rev-test",
        repo_name="repo",
        deadline_seconds=None,
    )

    server.complete_lifecycle(
        status="findings_detected",
        error="Notice: Chunk 1: model failed; baseline fallback disabled",
        elapsed_ms=12000.0,
        deadline_exceeded=False,
    )

    rec = server.get_lifecycle_record()
    assert rec.phase == "completed", f"Expected phase 'completed', got: {rec.phase}"
    assert rec.status == "findings_detected"
    assert rec.error == "Notice: Chunk 1: model failed; baseline fallback disabled"
    assert rec.deadline_exceeded is False
