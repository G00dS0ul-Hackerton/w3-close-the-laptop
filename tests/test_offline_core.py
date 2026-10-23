"""Tests proving the core SteadyDev engine functions 100% offline with network isolation."""

import socket
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from steadydev.git_collector import collect_review_packet_from_git
from steadydev.models import CheckReceipt
from steadydev.reviewer import Reviewer
from steadydev.server import create_server
from steadydev.store import SessionStore
from steadydev.telemetry import is_telemetry_enabled


def test_offline_core_isolated_from_external_network(
    temp_git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert that with all external network egress blocked, SteadyDev core runs with 100% success."""
    # 1. Enforce telemetry disabled
    monkeypatch.delenv("STEADYDEV_SENTRY_ENABLED", raising=False)
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert is_telemetry_enabled() is False

    # 2. Block external socket connections (allow loopback 127.0.0.1 only)
    orig_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0]
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ConnectionRefusedError(
                f"External network connection to {host} forbidden in offline core test!"
            )
        return orig_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)

    # 3. Create dirty diff and receipts
    readme = temp_git_repo / "README.md"
    readme.write_text("# Offline Project\nNew offline content\n", encoding="utf-8")

    receipt = CheckReceipt(
        receipt_id="rcpt-offline-01",
        command="pytest tests/offline_test.py",
        exit_code=0,
        output_summary="1 passed",
        timestamp_utc="2026-10-23T15:00:00Z",
    )

    # 4. Build packet
    packet = collect_review_packet_from_git(
        repo_path=temp_git_repo,
        session_intention="Offline test intention",
        acceptance_criteria=["Offline criterion 1"],
        check_receipts=[receipt],
    )
    assert len(packet.changed_files) == 1
    assert packet.snapshot_hash is not None

    # 5. Run Reviewer via deterministic offline baseline floor
    reviewer = Reviewer(ollama_client=MagicMock())
    result = reviewer.review(packet, model_name="baseline-checklist")
    assert result.status == "clean"
    assert result.model_name == "baseline-checklist"

    # 6. Store persistence in SQLite
    db_path = tmp_path / "offline_store.db"
    store = SessionStore(db_path=db_path)
    session = store.get_or_create_session(str(temp_git_repo), temp_git_repo.name)
    snap_id = store.save_snapshot(
        session_id=session["session_id"],
        git_head_sha=packet.git_head_sha or "0" * 40,
        diff_hash="d-1",
        untracked_hash="u-1",
        composite_hash=packet.snapshot_hash,
    )
    store.save_receipts(session["session_id"], snap_id, [receipt])
    store.save_findings(session["session_id"], snap_id, result.findings)

    # Verify retrieval
    stored_findings = store.get_findings(session["session_id"])
    assert len(stored_findings) == 0  # clean

    # 7. Start Loopback HTTP Server and test loopback communication
    server = create_server(
        temp_git_repo,
        port=0,
        token="offline-token",
        reviewer=reviewer,
        store=store,
        db_path=db_path,
    )
    import threading

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        headers = {"Authorization": "Bearer offline-token"}
        with httpx.Client(base_url=base_url, headers=headers, timeout=5.0) as client:
            res = client.get("/api/session")
            assert res.status_code == 200
            data = res.json()
            assert data["session_id"] == session["session_id"]

            # Test review deduplication over loopback
            res_rev = client.post(
                "/api/review",
                json={
                    "repo_path": str(temp_git_repo),
                    "check_receipts": [receipt.model_dump()],
                },
            )
            assert res_rev.status_code == 200
            assert res_rev.json().get("unchanged_snapshot") is True
    finally:
        server.shutdown()
        server.server_close()
