"""Tests for worker scheduling, single-worker slot, fingerprint deduplication, and mid-flight staleness fencing."""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import httpx

from steadydev.models import ReviewResult
from steadydev.server import create_server
from steadydev.store import SessionStore


def test_review_fingerprint_deduplication(temp_git_repo: Path, tmp_path: Path) -> None:
    """Verify that repeated review requests on unchanged working trees return immediately via deduplication."""
    db_path = tmp_path / "test_dedup.db"
    store = SessionStore(db_path=db_path)

    # Modify a file to make repo dirty
    readme = temp_git_repo / "README.md"
    readme.write_text("# Updated Title\nNew changes\n", encoding="utf-8")

    mock_reviewer = MagicMock()
    mock_reviewer.review.return_value = ReviewResult(
        packet_id="pkt-1",
        status="clean",
        model_name="gemma3:4b",
        findings=[],
        retired_finding_ids=[],
        closing_summary="Tested changes.",
        restart_note="Continue with step 2.",
        timing_ms={"total_duration_ms": 12000.0},
    )

    server = create_server(
        temp_git_repo,
        port=0,
        token="test-token-123",
        reviewer=mock_reviewer,
        store=store,
        db_path=db_path,
    )
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.1)

    base_url = f"http://127.0.0.1:{server.server_port}"
    headers = {"Authorization": "Bearer test-token-123"}
    body = {
        "repo_path": str(temp_git_repo),
        "session_intention": "Test deduplication",
        "acceptance_criteria": ["C1"],
        "check_receipts": [
            {
                "receipt_id": "r1",
                "command": "pytest",
                "exit_code": 0,
                "output_summary": "1 passed",
                "timestamp_utc": "2026-10-23T15:00:00Z",
            }
        ],
    }

    try:
        with httpx.Client(base_url=base_url, headers=headers, timeout=10.0) as client:
            # First review: must execute model
            res1 = client.post("/api/review", json=body)
            assert res1.status_code == 200
            data1 = res1.json()
            assert data1["status"] == "clean"
            assert mock_reviewer.review.call_count == 1

            # Second review: identical repo state -> must deduplicate in <200ms
            start_t = time.monotonic()
            res2 = client.post("/api/review", json=body)
            elapsed_ms = (time.monotonic() - start_t) * 1000.0

            assert res2.status_code == 200
            data2 = res2.json()
            assert data2["status"] == "unchanged_snapshot"
            assert data2["unchanged_snapshot"] is True
            assert elapsed_ms < 500.0  # sub-second deduplication
            assert mock_reviewer.review.call_count == 1  # model was NOT called again!

            # Third review with force_refresh=True -> must execute model
            body_force = dict(body)
            body_force["force_refresh"] = True
            res3 = client.post("/api/review", json=body_force)
            assert res3.status_code == 200
            assert mock_reviewer.review.call_count == 2
    finally:
        server.shutdown()
        server.server_close()


def test_review_rejects_mid_flight_git_mutation(
    temp_git_repo: Path, tmp_path: Path
) -> None:
    """Verify that if the working tree mutates while review is in progress, findings are discarded."""
    db_path = tmp_path / "test_mid_flight.db"
    store = SessionStore(db_path=db_path)

    readme = temp_git_repo / "README.md"
    readme.write_text("# Initial State\n", encoding="utf-8")

    review_started = threading.Event()
    continue_review = threading.Event()

    def blocking_review(*args, **kwargs):
        review_started.set()
        continue_review.wait(timeout=5.0)
        return ReviewResult(
            packet_id="pkt-stale",
            status="clean",
            model_name="gemma3:4b",
            findings=[],
            retired_finding_ids=[],
            closing_summary="Stale summary",
            restart_note="Stale restart note",
        )

    mock_reviewer = MagicMock()
    mock_reviewer.review.side_effect = blocking_review

    server = create_server(
        temp_git_repo,
        port=0,
        token="token-mid-flight",
        reviewer=mock_reviewer,
        store=store,
        db_path=db_path,
    )
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.1)

    base_url = f"http://127.0.0.1:{server.server_port}"
    headers = {"Authorization": "Bearer token-mid-flight"}
    body = {
        "repo_path": str(temp_git_repo),
        "session_intention": "Test staleness",
        "acceptance_criteria": ["C1"],
    }

    try:
        with httpx.Client(base_url=base_url, headers=headers, timeout=10.0) as client:
            # Launch review in background thread
            review_resp: dict = {}

            def run_req():
                res = client.post("/api/review", json=body)
                review_resp["status_code"] = res.status_code
                review_resp["data"] = res.json()

            req_thread = threading.Thread(target=run_req)
            req_thread.start()

            # Wait for review to start
            assert review_started.wait(timeout=2.0) is True

            # Mutate working tree while review is running
            readme.write_text("# Mutated Mid Flight\nExtra line\n", encoding="utf-8")

            # Allow review to complete
            continue_review.set()
            req_thread.join(timeout=3.0)

            # Assert server rejected stale review with 409
            assert review_resp.get("status_code") == 409
            assert review_resp.get("data", {}).get("code") == "stale_snapshot"
            assert (
                "changed during review"
                in review_resp.get("data", {}).get("message", "").lower()
            )
    finally:
        server.shutdown()
        server.server_close()


def test_single_worker_concurrency_saturation(
    temp_git_repo: Path, tmp_path: Path
) -> None:
    """Verify single-worker slot immediately rejects concurrent review requests with 409."""
    db_path = tmp_path / "test_concurrency.db"
    store = SessionStore(db_path=db_path)

    review_active = threading.Event()
    finish_review = threading.Event()

    def slow_review(*args, **kwargs):
        review_active.set()
        finish_review.wait(timeout=5.0)
        return ReviewResult(
            packet_id="pkt-slow",
            status="clean",
            model_name="gemma3:4b",
            findings=[],
            retired_finding_ids=[],
            closing_summary="Slow summary",
            restart_note="Slow note",
        )

    mock_reviewer = MagicMock()
    mock_reviewer.review.side_effect = slow_review

    server = create_server(
        temp_git_repo,
        port=0,
        token="token-worker",
        reviewer=mock_reviewer,
        store=store,
        db_path=db_path,
    )
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.1)

    base_url = f"http://127.0.0.1:{server.server_port}"
    headers = {"Authorization": "Bearer token-worker"}
    body = {
        "repo_path": str(temp_git_repo),
        "session_intention": "Test concurrency",
        "acceptance_criteria": ["C1"],
    }

    try:
        with httpx.Client(base_url=base_url, headers=headers, timeout=10.0) as client:
            worker_thread = threading.Thread(
                target=lambda: client.post("/api/review", json=body)
            )
            worker_thread.start()

            assert review_active.wait(timeout=2.0) is True

            # Attempt 5 concurrent requests while worker is busy
            for _ in range(5):
                res = client.post("/api/review", json=body)
                assert res.status_code == 409
                assert res.json().get("code") == "review_in_progress"

            finish_review.set()
            worker_thread.join(timeout=3.0)
    finally:
        server.shutdown()
        server.server_close()


def test_session_pause_and_resume(temp_git_repo: Path, tmp_path: Path) -> None:
    """Verify pause blocks review execution and resume unblocks it."""
    db_path = tmp_path / "test_pause.db"
    store = SessionStore(db_path=db_path)

    mock_reviewer = MagicMock()
    mock_reviewer.review.return_value = ReviewResult(
        packet_id="pkt-pause",
        status="clean",
        model_name="gemma3:4b",
        findings=[],
        retired_finding_ids=[],
        closing_summary="Pause summary",
        restart_note="Pause note",
    )

    server = create_server(
        temp_git_repo,
        port=0,
        token="token-pause",
        reviewer=mock_reviewer,
        store=store,
        db_path=db_path,
    )
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.1)

    base_url = f"http://127.0.0.1:{server.server_port}"
    headers = {"Authorization": "Bearer token-pause"}
    body = {"repo_path": str(temp_git_repo)}

    try:
        with httpx.Client(base_url=base_url, headers=headers, timeout=10.0) as client:
            # 1. Pause session
            res_pause = client.post("/api/session/pause", json=body)
            assert res_pause.status_code == 200
            assert res_pause.json().get("is_paused") is True

            # 2. Review while paused -> 409 review_paused
            res_rev = client.post("/api/review", json=body)
            assert res_rev.status_code == 409
            assert res_rev.json().get("code") == "review_paused"
            assert mock_reviewer.review.call_count == 0

            # 3. Resume session
            res_res = client.post("/api/session/resume", json=body)
            assert res_res.status_code == 200
            assert res_res.json().get("is_paused") is False

            # 4. Review after resume -> 200 OK
            res_rev2 = client.post("/api/review", json=body)
            assert res_rev2.status_code == 200
            assert mock_reviewer.review.call_count == 1
    finally:
        server.shutdown()
        server.server_close()
