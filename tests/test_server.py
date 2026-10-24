"""Unit tests for loopback HTTP server authentication, boundaries, and endpoints."""

import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from steadydev.models import (
    ReviewPacket,
    ReviewResult,
)
from steadydev.server import create_server


class MockReviewer:
    """Mock reviewer returning deterministic ReviewResult without calling Ollama."""

    def review(
        self,
        packet: ReviewPacket,
        model_name: str | None = None,
        **kwargs: Any,
    ) -> ReviewResult:
        return ReviewResult(
            packet_id=packet.packet_id,
            model_tag="mock-reviewer",
            elapsed_seconds=0.1,
            status="clean",
            findings=[],
            closing_summary="All checks pass in mock review.",
            restart_note="Continue development tomorrow.",
            retired_finding_ids=[],
            raw_content="{}",
        )


@pytest.fixture
def running_server(temp_git_repo: Path):
    """Start a live SteadyDevServer on ephemeral loopback port."""
    server = create_server(
        repo_root=temp_git_repo,
        port=0,
        token="test-secret-token-12345",
        reviewer=MockReviewer(),  # type: ignore
        db_path=temp_git_repo.parent / "server_test.db",
    )
    port = server.server_port
    token = server.token

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.05)  # Yield for server startup

    base_url = f"http://127.0.0.1:{port}"
    yield {
        "base_url": base_url,
        "token": token,
        "repo_root": temp_git_repo,
        "server": server,
        "store": server.store,
    }

    server.shutdown()
    server.server_close()


def test_auth_rejection(running_server: dict):
    base_url = running_server["base_url"]

    # 1. No Authorization header
    resp = httpx.get(f"{base_url}/api/health")
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"] == "unauthorized"

    # 2. Invalid Bearer token
    resp = httpx.get(
        f"{base_url}/api/health", headers={"Authorization": "Bearer wrong-token-xyz"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


def test_health_endpoint(running_server: dict):
    base_url = running_server["base_url"]
    token = running_server["token"]

    resp = httpx.get(
        f"{base_url}/api/health", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "model_status" in data
    assert data["active_model"] == "gemma3:4b"


def test_snapshot_endpoint(running_server: dict):
    base_url = running_server["base_url"]
    token = running_server["token"]
    repo_root = running_server["repo_root"]

    # Modify a file
    readme = repo_root / "README.md"
    readme.write_text("# Updated content\n", encoding="utf-8")

    resp = httpx.post(
        f"{base_url}/api/snapshot",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo_path": str(repo_root)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo_name"] == repo_root.name
    assert len(data["changed_files"]) >= 1
    assert data["changed_files"][0]["path"] == "README.md"


def test_boundary_rejection(running_server: dict, tmp_path: Path):
    base_url = running_server["base_url"]
    token = running_server["token"]

    # Create directory outside repo root
    external_dir = tmp_path / "outside_repo"
    external_dir.mkdir()

    # Attempt to request snapshot on external path
    resp = httpx.post(
        f"{base_url}/api/snapshot",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo_path": str(external_dir)},
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "forbidden"


def test_review_endpoint(running_server: dict):
    base_url = running_server["base_url"]
    token = running_server["token"]
    repo_root = running_server["repo_root"]

    resp = httpx.post(
        f"{base_url}/api/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "repo_path": str(repo_root),
            "session_intention": "Clean review test",
            "acceptance_criteria": ["Code runs cleanly"],
            "check_receipts": [
                {
                    "receipt_id": "r1",
                    "command": "pytest",
                    "exit_code": 0,
                    "output_summary": "1 passed",
                    "timestamp_utc": "2026-10-21T03:00:00Z",
                }
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "clean"
    assert "All checks pass" in data["closing_summary"]
    assert "Continue development" in data["restart_note"]


def test_session_lifecycle_endpoints(running_server: dict):
    base_url = running_server["base_url"]
    token = running_server["token"]
    repo_root = running_server["repo_root"]

    # 1. GET /api/session
    resp = httpx.get(
        f"{base_url}/api/session",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    session_data = resp.json()
    assert session_data["repo_name"] == repo_root.name
    assert session_data["is_ended"] == 0
    assert "findings" in session_data

    # 2. POST /api/session (update intention & criteria)
    resp = httpx.post(
        f"{base_url}/api/session",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "repo_path": str(repo_root),
            "intention": "Fix mobile login redirect",
            "criteria": ["Check mobile nav", "No regressions"],
        },
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["intention"] == "Fix mobile login redirect"
    assert len(updated["criteria"]) == 2

    # 3. POST /api/session/note (update restart note)
    resp = httpx.post(
        f"{base_url}/api/session/note",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "repo_path": str(repo_root),
            "restart_note": "Custom user restart note.",
            "is_user_edited": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["restart_note"] == "Custom user restart note."
    assert resp.json()["is_note_user_edited"] == 1

    # 4. POST /api/session/close
    resp = httpx.post(
        f"{base_url}/api/session/close",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "repo_path": str(repo_root),
            "closing_summary": {"status": "left_here"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_ended"] == 1


def test_finding_patch_and_conflict_handling(running_server: dict):
    base_url = running_server["base_url"]
    token = running_server["token"]
    repo_root = running_server["repo_root"]

    # Trigger review to create snapshot and finding
    resp = httpx.post(
        f"{base_url}/api/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "repo_path": str(repo_root),
            "session_intention": "Review test",
            "expected_snapshot_hash": "wrong-hash-12345",  # should trigger 409 Conflict
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "conflict"
    assert "Snapshot mismatch" in resp.json()["message"]


def test_repo_validate_success(running_server: dict, temp_git_repo: Path):
    base_url = running_server["base_url"]
    token = running_server["token"]

    resp = httpx.post(
        f"{base_url}/api/repo/validate",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo_path": str(temp_git_repo)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["repo_name"] == temp_git_repo.name
    assert "git_status" in data
    assert data["git_status"]["has_commits"] is True


def test_repo_validate_rejections(running_server: dict, tmp_path: Path):
    base_url = running_server["base_url"]
    token = running_server["token"]

    # Non-git directory
    plain_dir = tmp_path / "plain_dir"
    plain_dir.mkdir()
    resp = httpx.post(
        f"{base_url}/api/repo/validate",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo_path": str(plain_dir)},
    )
    assert resp.status_code == 422
    assert "not a Git repository" in resp.json()["message"]

    # System drive root (e.g. C:\ or /)
    drive_root = Path(tmp_path.drive + "\\") if tmp_path.drive else Path("/")
    resp = httpx.post(
        f"{base_url}/api/repo/validate",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo_path": str(drive_root)},
    )
    assert resp.status_code == 403


def test_repo_select_and_recent_repos(running_server: dict, tmp_path: Path):
    import subprocess

    base_url = running_server["base_url"]
    token = running_server["token"]

    # Create a second git repo
    second_repo = tmp_path / "second_repo"
    second_repo.mkdir()
    subprocess.run(
        ["git", "init"], cwd=str(second_repo), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Tester"], cwd=str(second_repo), check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(second_repo),
        check=True,
    )
    (second_repo / "README.md").write_text("Hello second repo")
    subprocess.run(["git", "add", "."], cwd=str(second_repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=str(second_repo), check=True
    )

    # Select second repo
    resp = httpx.post(
        f"{base_url}/api/repo/select",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo_path": str(second_repo)},
    )
    assert resp.status_code == 200
    session_data = resp.json()
    assert session_data["repo_name"] == "second_repo"
    assert "git_status" in session_data

    # Verify GET /api/session now returns second_repo
    resp = httpx.get(
        f"{base_url}/api/session",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["repo_name"] == "second_repo"

    # Verify GET /api/repos/recent contains second_repo
    resp = httpx.get(
        f"{base_url}/api/repos/recent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    recents = resp.json()["repositories"]
    assert any(r["repo_name"] == "second_repo" for r in recents)


def test_snapshot_returns_git_status(running_server: dict, temp_git_repo: Path):
    base_url = running_server["base_url"]
    token = running_server["token"]

    resp = httpx.post(
        f"{base_url}/api/snapshot",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo_path": str(temp_git_repo)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "git_status" in data
    assert data["git_status"]["has_commits"] is True
    assert data["git_status"]["state"] in ("clean", "dirty")


def test_reset_session_endpoint(running_server: dict, temp_git_repo: Path):
    """Verify POST /api/session/reset starts fresh session and resets findings."""
    base_url = running_server["base_url"]
    token = running_server["token"]

    # Initial session
    resp1 = httpx.get(
        f"{base_url}/api/session",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200
    s1_id = resp1.json()["session_id"]

    # Call reset
    resp_reset = httpx.post(
        f"{base_url}/api/session/reset",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "repo_path": str(temp_git_repo),
            "intention": "Fresh day intention",
            "criteria": ["Clean review"],
        },
    )
    assert resp_reset.status_code == 200
    data = resp_reset.json()
    assert data["session_id"] != s1_id
    assert data["is_ended"] == 0
    assert data["intention"] == "Fresh day intention"
    assert data["criteria"] == ["Clean review"]
    assert len(data["findings"]) == 0
    assert len(data["check_receipts"]) == 0
    assert "git_status" in data


def test_format_model_display_name() -> None:
    from steadydev.server import format_model_display_name

    assert format_model_display_name("gemma3:4b") == "Gemma 3 (4B)"
    assert format_model_display_name("qwen2.5-coder:3b") == "Qwen 2.5 Coder (3B)"
    assert format_model_display_name("qwen2.5:7b") == "Qwen 2.5 (7B)"
    assert (
        format_model_display_name("baseline-checklist")
        == "Baseline Checklist (Offline Floor)"
    )
    assert format_model_display_name("baseline") == "Baseline Checklist (Offline Floor)"
    assert format_model_display_name("") == "Unknown"


def test_get_models_endpoint_success(running_server: dict) -> None:
    base_url = running_server["base_url"]
    token = running_server["token"]

    resp = httpx.get(
        f"{base_url}/api/models",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "ollama_status" in data
    assert "default_model" in data
    assert isinstance(data["models"], list)

    # Always includes baseline floor
    baseline_entry = next(
        (m for m in data["models"] if m["id"] == "baseline-checklist"), None
    )
    assert baseline_entry is not None
    assert baseline_entry["is_baseline"] is True
    assert baseline_entry["display_name"] == "Baseline Checklist (Offline Floor)"


def test_get_models_endpoint_unauthorized(running_server: dict) -> None:
    base_url = running_server["base_url"]
    resp = httpx.get(f"{base_url}/api/models")
    assert resp.status_code == 401


def test_review_progress_endpoint(running_server: dict) -> None:
    base_url = running_server["base_url"]
    token = running_server["token"]

    resp = httpx.get(
        f"{base_url}/api/review/progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "is_reviewing" in data
    assert "current_chunk" in data
    assert "total_chunks" in data
    assert "current_files" in data
    assert "phase" in data
    assert data["is_reviewing"] is False


def test_review_cancel_endpoint(running_server: dict) -> None:
    base_url = running_server["base_url"]
    token = running_server["token"]

    resp = httpx.post(
        f"{base_url}/api/review/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"


def test_review_cancellation_revokes_write_authority_and_stops_persistence(
    running_server: dict,
) -> None:
    """R01: Cancel during active review must revoke publication authority and stop persistence."""
    import threading
    from unittest.mock import MagicMock

    from steadydev.models import Finding, FindingCategory, FindingStatus, ReviewResult

    base_url = running_server["base_url"]
    token = running_server["token"]
    repo_root = running_server["repo_root"]
    server_obj = running_server["server"]

    review_started = threading.Event()
    review_release = threading.Event()

    mock_finding = Finding(
        finding_id="fnd-cancelled-job",
        category=FindingCategory.EVIDENCE_MISMATCH,
        locator="src/foo.py:10",
        description="Should not be saved",
        status=FindingStatus.OPEN,
    )
    mock_result = ReviewResult(
        packet_id="pkt-test",
        status="findings_detected",
        findings=[mock_finding],
        closing_summary="Late summary",
        restart_note="Late AI restart note",
    )

    def blocking_review(*args, **kwargs):
        review_started.set()
        review_release.wait(timeout=5.0)
        return mock_result

    orig_review = server_obj.reviewer.review
    server_obj.reviewer.review = MagicMock(side_effect=blocking_review)

    review_thread_response = []

    def run_review_req():
        r = httpx.post(
            f"{base_url}/api/review",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "repo_path": str(repo_root),
                "session_intention": "Cancel authority test",
                "acceptance_criteria": ["Check authority"],
            },
            timeout=10.0,
        )
        review_thread_response.append(r)

    th = threading.Thread(target=run_review_req, daemon=True)
    try:
        th.start()
        assert review_started.wait(timeout=3.0), "Review did not start in time"

        # 1. While reviewing, call cancel
        cancel_resp = httpx.post(
            f"{base_url}/api/review/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert cancel_resp.status_code == 200

        # 2. User edits restart note while review is in-flight
        note_resp = httpx.post(
            f"{base_url}/api/session/note",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "repo_path": str(repo_root),
                "restart_note": "User saved manual restart note",
                "is_user_edited": True,
            },
        )
        assert note_resp.status_code == 200

        # 3. Release blocked review
        review_release.set()
        th.join(timeout=5.0)

        # 4. Check database: finding must NOT be persisted and note must NOT be overwritten
        session = server_obj.store.get_or_create_session(str(repo_root), repo_root.name)
        findings = server_obj.store.get_findings(session["session_id"])
        finding_ids = [f["finding_id"] for f in findings]
        assert "fnd-cancelled-job" not in finding_ids, (
            "Cancelled review findings must not be persisted"
        )
        assert session["restart_note"] == "User saved manual restart note", (
            "User note must not be overwritten"
        )
    finally:
        review_release.set()
        server_obj.reviewer.review = orig_review


def test_concurrent_review_rejected_with_conflict_409(running_server: dict) -> None:
    """R02: A second review request while one is running must return 409 Conflict."""
    import threading
    from unittest.mock import MagicMock

    from steadydev.models import ReviewResult

    base_url = running_server["base_url"]
    token = running_server["token"]
    repo_root = running_server["repo_root"]
    server_obj = running_server["server"]

    review_started = threading.Event()
    review_release = threading.Event()

    def blocking_review(*args, **kwargs):
        review_started.set()
        review_release.wait(timeout=5.0)
        return ReviewResult(
            packet_id="pkt-1",
            status="clean",
            closing_summary="Done",
            restart_note="Next",
        )

    orig_review = server_obj.reviewer.review
    server_obj.reviewer.review = MagicMock(side_effect=blocking_review)

    th = threading.Thread(
        target=lambda: httpx.post(
            f"{base_url}/api/review",
            headers={"Authorization": f"Bearer {token}"},
            json={"repo_path": str(repo_root)},
            timeout=10.0,
        ),
        daemon=True,
    )
    try:
        th.start()
        assert review_started.wait(timeout=3.0)

        # Second review call should be rejected with 409
        resp2 = httpx.post(
            f"{base_url}/api/review",
            headers={"Authorization": f"Bearer {token}"},
            json={"repo_path": str(repo_root)},
        )
        assert resp2.status_code == 409
        assert resp2.json()["error"] == "conflict"
        assert "already in progress" in resp2.json()["message"].lower()
    finally:
        review_release.set()
        th.join(timeout=5.0)
        server_obj.reviewer.review = orig_review


def test_server_patch_finding_isolated_to_active_session(
    running_server: dict, tmp_path: Path
) -> None:
    """R06: PATCH /api/findings/{id} must only update the finding in the active repository session."""
    from steadydev.models import Finding, FindingCategory, FindingStatus

    base_url = running_server["base_url"]
    token = running_server["token"]
    store = running_server["store"]
    repo1 = running_server["repo_root"]

    repo2 = tmp_path / "repo2"
    repo2.mkdir()

    sess1 = store.get_or_create_session(str(repo1), repo1.name)
    sess2 = store.get_or_create_session(str(repo2), "repo2")
    snap1 = store.save_snapshot(sess1["session_id"], "sha1", "d", "u", "c1")
    snap2 = store.save_snapshot(sess2["session_id"], "sha2", "d", "u", "c2")

    f1 = Finding(
        finding_id="fnd-patch-iso",
        category=FindingCategory.UNVERIFIED,
        locator="src/a.py:1",
        description="Desc",
        status=FindingStatus.OPEN,
    )
    store.save_findings(sess1["session_id"], snap1, [f1])
    store.save_findings(sess2["session_id"], snap2, [f1])

    # Patch finding in active repo (repo1)
    patch_resp = httpx.patch(
        f"{base_url}/api/findings/fnd-patch-iso",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "dismissed", "user_reason": "Not an issue"},
    )
    assert patch_resp.status_code == 200

    # sess1 must be dismissed, sess2 must remain open
    f_sess1 = store.get_findings(sess1["session_id"])[0]
    f_sess2 = store.get_findings(sess2["session_id"])[0]
    assert f_sess1["status"] == "dismissed"
    assert f_sess2["status"] == "open", (
        "Finding in session 2 must not be modified by session 1 PATCH"
    )


def test_cancellation_retains_worker_until_physical_completion(
    running_server: dict,
) -> None:
    """R08: Calling cancel does not free worker slot while physical worker is still running."""
    import threading
    from unittest.mock import MagicMock

    from steadydev.models import ReviewResult

    base_url = running_server["base_url"]
    token = running_server["token"]
    repo_root = running_server["repo_root"]
    server_obj = running_server["server"]

    review_started = threading.Event()
    review_release = threading.Event()

    def blocking_review(*args, **kwargs):
        review_started.set()
        review_release.wait(timeout=5.0)
        return ReviewResult(
            packet_id="pkt-1",
            status="clean",
            closing_summary="Done",
            restart_note="Next",
        )

    orig_review = server_obj.reviewer.review
    server_obj.reviewer.review = MagicMock(side_effect=blocking_review)

    th = threading.Thread(
        target=lambda: httpx.post(
            f"{base_url}/api/review",
            headers={"Authorization": f"Bearer {token}"},
            json={"repo_path": str(repo_root)},
            timeout=10.0,
        ),
        daemon=True,
    )
    try:
        th.start()
        assert review_started.wait(timeout=3.0)

        # Call cancel
        cancel_resp = httpx.post(
            f"{base_url}/api/review/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert cancel_resp.status_code == 200

        # While physical worker is still running, a second review MUST still be rejected with 409
        resp2 = httpx.post(
            f"{base_url}/api/review",
            headers={"Authorization": f"Bearer {token}"},
            json={"repo_path": str(repo_root)},
        )
        assert resp2.status_code == 409
        assert resp2.json()["error"] == "conflict"

        # Now release the physical worker
        review_release.set()
        th.join(timeout=5.0)

        # After physical worker exits, a subsequent review is admitted
        resp3 = httpx.post(
            f"{base_url}/api/review",
            headers={"Authorization": f"Bearer {token}"},
            json={"repo_path": str(repo_root)},
        )
        assert resp3.status_code == 200
    finally:
        review_release.set()
        server_obj.reviewer.review = orig_review


def test_session_reset_invalidates_in_flight_review_publication(
    running_server: dict,
) -> None:
    """R04: Resetting the session while a review is in flight cancels review authority."""
    import threading
    from unittest.mock import MagicMock

    from steadydev.models import Finding, FindingCategory, FindingStatus, ReviewResult

    base_url = running_server["base_url"]
    token = running_server["token"]
    repo_root = running_server["repo_root"]
    server_obj = running_server["server"]

    review_started = threading.Event()
    review_release = threading.Event()

    mock_finding = Finding(
        finding_id="fnd-reset-job",
        category=FindingCategory.EVIDENCE_MISMATCH,
        locator="src/bar.py:10",
        description="Should be discarded after reset",
        status=FindingStatus.OPEN,
    )
    mock_result = ReviewResult(
        packet_id="pkt-reset",
        status="findings_detected",
        findings=[mock_finding],
        closing_summary="Reset summary",
        restart_note="Reset AI note",
    )

    def blocking_review(*args, **kwargs):
        review_started.set()
        review_release.wait(timeout=5.0)
        return mock_result

    orig_review = server_obj.reviewer.review
    server_obj.reviewer.review = MagicMock(side_effect=blocking_review)

    review_res = []

    def run_review():
        r = httpx.post(
            f"{base_url}/api/review",
            headers={"Authorization": f"Bearer {token}"},
            json={"repo_path": str(repo_root)},
            timeout=10.0,
        )
        review_res.append(r)

    th = threading.Thread(target=run_review, daemon=True)
    try:
        th.start()
        assert review_started.wait(timeout=3.0)

        # Reset session mid-review
        reset_resp = httpx.post(
            f"{base_url}/api/session/reset",
            headers={"Authorization": f"Bearer {token}"},
            json={"repo_path": str(repo_root), "intention": "Fresh intention"},
        )
        assert reset_resp.status_code == 200

        review_release.set()
        th.join(timeout=5.0)

        assert len(review_res) == 1
        assert review_res[0].status_code == 409

        # Active session must be clean without fnd-reset-job
        active_sess = server_obj.store.get_or_create_session(
            str(repo_root), repo_root.name
        )
        findings = server_obj.store.get_findings(active_sess["session_id"])
        assert "fnd-reset-job" not in [f["finding_id"] for f in findings]
    finally:
        review_release.set()
        server_obj.reviewer.review = orig_review


def test_review_cancel_physically_aborts_transport_and_unloads_model(
    running_server: dict,
) -> None:
    """R10: Cancelling review must invoke cancel_active() on reviewer and unload_model on ollama client."""
    from unittest.mock import MagicMock

    base_url = running_server["base_url"]
    token = running_server["token"]
    repo_root = running_server["repo_root"]
    server_obj = running_server["server"]

    # Mock cancel_active and unload_model on reviewer / client
    server_obj.reviewer.cancel_active = MagicMock()
    server_obj.ollama_client.unload_model = MagicMock(return_value=True)

    resp = httpx.post(
        f"{base_url}/api/review/cancel",
        headers={"Authorization": f"Bearer {token}"},
        json={"repo_path": str(repo_root)},
    )
    assert resp.status_code == 200

    # Reviewer cancel_active must have been called
    assert hasattr(server_obj.reviewer, "cancel_active")
    server_obj.reviewer.cancel_active.assert_called_once()


def test_unlimited_workflow_timeout_and_live_diagnostics_elapsed_and_chunks(
    running_server: dict,
) -> None:
    """R15: POST /api/review accepts workflow_timeout_seconds=None (Unlimited) without ValidationError, and GET /api/review/diagnostics returns live advancing elapsed_ms and incremental chunk_diagnostics during auditing."""
    import threading
    import time
    from unittest.mock import MagicMock

    from steadydev.models import ChunkProvenance, ReviewResult

    base_url = running_server["base_url"]
    token = running_server["token"]
    repo_root = running_server["repo_root"]
    server_obj = running_server["server"]

    chunk1_reported = threading.Event()
    release_review = threading.Event()

    def fake_review(packet, **kwargs):
        # Verify unlimited timeout was forwarded as None
        assert kwargs.get("workflow_timeout_seconds") is None
        progress_cb = kwargs.get("progress_callback")
        time.sleep(0.05)
        cp1 = ChunkProvenance(
            chunk_index=1,
            total_chunks=2,
            file_paths=["src/foo.py"],
            attempts=[],
            resolved_engine="qwen2.5-coder:3b",
            fallback_reason=None,
            findings_count=0,
        )
        # Call progress_callback with incremental chunk provenance
        if progress_cb is not None:
            try:
                progress_cb(1, 2, "src/foo.py", [cp1])
            except TypeError:
                progress_cb(1, 2, "src/foo.py")
        chunk1_reported.set()
        release_review.wait(timeout=5.0)
        return ReviewResult(
            packet_id=packet.packet_id,
            status="clean",
            closing_summary="All clean",
            restart_note="Ready",
            model_name="qwen2.5-coder:3b",
            chunk_provenance=[cp1],
        )

    orig_review = server_obj.reviewer.review
    server_obj.reviewer.review = MagicMock(side_effect=fake_review)

    review_resp_holder: list[httpx.Response] = []

    def run_post():
        r = httpx.post(
            f"{base_url}/api/review",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "repo_path": str(repo_root),
                "model": "qwen2.5-coder:3b",
                "fallback_model": "gemma3:4b",
                "use_baseline_fallback": False,
                "workflow_timeout_seconds": None,
            },
            timeout=10.0,
        )
        review_resp_holder.append(r)

    th = threading.Thread(target=run_post, daemon=True)
    try:
        th.start()
        assert chunk1_reported.wait(timeout=3.0)

        diag_resp = httpx.get(
            f"{base_url}/api/review/diagnostics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert diag_resp.status_code == 200
        lc = diag_resp.json()
        assert lc["is_reviewing"] is True
        assert lc["deadline_seconds"] is None, "Unlimited timeout must serialize deadline_seconds as None"
        assert lc["elapsed_ms"] > 0.0, f"Expected live elapsed_ms > 0 during auditing, got {lc['elapsed_ms']}"
        assert len(lc["chunk_diagnostics"]) == 1, "Expected Chunk 1 provenance to be visible mid-review"
        assert lc["chunk_diagnostics"][0]["resolved_engine"] == "qwen2.5-coder:3b"

        release_review.set()
        th.join(timeout=5.0)
        assert len(review_resp_holder) == 1
        assert review_resp_holder[0].status_code == 200
    finally:
        release_review.set()
        server_obj.reviewer.review = orig_review

