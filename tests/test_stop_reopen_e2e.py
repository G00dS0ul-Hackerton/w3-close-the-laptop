"""End-to-end verification of durable stopping and restart across process lifecycles (M3)."""

import subprocess
import threading
import time
from pathlib import Path

import httpx

from steadydev.models import (
    Finding,
    FindingCategory,
    FindingStatus,
    ReviewPacket,
    ReviewResult,
)
from steadydev.server import create_server
from steadydev.store import SessionStore


class StubReviewer:
    """Deterministic reviewer for end-to-end testing."""

    def review(self, packet: ReviewPacket, **kwargs) -> ReviewResult:
        f1 = Finding(
            finding_id="fnd-login-redirect",
            category=FindingCategory.UNVERIFIED,
            locator="src/auth.py:42",
            description="Login redirect needs mobile viewport check",
            status=FindingStatus.OPEN,
        )
        f2 = Finding(
            finding_id="fnd-readme-stale",
            category=FindingCategory.NEEDS_JUDGMENT,
            locator="README.md:1",
            description="Setup guide references /welcome instead of /dashboard",
            status=FindingStatus.OPEN,
        )
        return ReviewResult(
            packet_id=packet.packet_id,
            status="findings_detected",
            findings=[f1, f2],
            closing_summary="Found 2 items needing attention.",
            restart_note="Model default restart note.",
            retired_finding_ids=[],
        )


def test_durable_stop_and_reopen_lifecycle(temp_git_repo: Path, tmp_path: Path) -> None:
    """Full lifecycle: start session, resolve finding, edit note, close, restart process, verify state."""
    db_file = tmp_path / "persistent_steadydev.db"
    token = "test-e2e-token"

    # --- PHASE 1: Initial Session & Review ---
    store1 = SessionStore(db_path=db_file)
    server1 = create_server(
        repo_root=temp_git_repo,
        port=0,
        token=token,
        reviewer=StubReviewer(),  # type: ignore
        store=store1,
    )
    port1 = server1.server_port
    t1 = threading.Thread(target=server1.serve_forever, daemon=True)
    t1.start()
    time.sleep(0.05)
    base_url1 = f"http://127.0.0.1:{port1}"
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Update Intention and Criteria
    resp = httpx.post(
        f"{base_url1}/api/session",
        headers=headers,
        json={
            "repo_path": str(temp_git_repo),
            "intention": "Fix mobile login redirect and dashboard",
            "criteria": ["Mobile navigation at 390px", "Auth tests pass"],
        },
    )
    assert resp.status_code == 200

    # 2. Trigger Review (creates findings in store)
    resp = httpx.post(
        f"{base_url1}/api/review",
        headers=headers,
        json={"repo_path": str(temp_git_repo)},
    )
    assert resp.status_code == 200
    review_data = resp.json()
    assert len(review_data["findings"]) == 2

    # 3. User resolves Finding 1 with manual audit note
    resp = httpx.patch(
        f"{base_url1}/api/findings/fnd-login-redirect",
        headers=headers,
        json={
            "status": "user-reported-resolved",
            "user_reason": "Verified manually in Chrome mobile emulator at 390px",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "user-reported-resolved"

    # 4. User defers Finding 2
    resp = httpx.patch(
        f"{base_url1}/api/findings/fnd-readme-stale",
        headers=headers,
        json={
            "status": "deferred",
            "user_reason": "Doc updates deferred until PR review",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deferred"

    # 5. User edits restart note
    custom_restart_note = "Pick up with mobile auth navigation tests tomorrow morning."
    resp = httpx.post(
        f"{base_url1}/api/session/note",
        headers=headers,
        json={
            "repo_path": str(temp_git_repo),
            "restart_note": custom_restart_note,
            "is_user_edited": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["restart_note"] == custom_restart_note

    # 6. User clicks "Leave it here" (close session)
    resp = httpx.post(
        f"{base_url1}/api/session/close",
        headers=headers,
        json={
            "repo_path": str(temp_git_repo),
            "closing_summary": {"left_here": True},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_ended"] == 1

    # Verify NO git commits were made by closing
    git_log = subprocess.run(
        ["git", "log", "-n", "1", "--oneline"],
        cwd=str(temp_git_repo),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Initial commit" in git_log.stdout

    # Graceful shutdown of server 1
    resp = httpx.post(f"{base_url1}/api/shutdown", headers=headers)
    assert resp.status_code == 200
    t1.join(timeout=2.0)
    server1.server_close()

    # --- PHASE 2: Fresh Process Restart & Reopen ---
    store2 = SessionStore(db_path=db_file)
    server2 = create_server(
        repo_root=temp_git_repo,
        port=0,
        token=token,
        reviewer=StubReviewer(),  # type: ignore
        store=store2,
    )
    port2 = server2.server_port
    t2 = threading.Thread(target=server2.serve_forever, daemon=True)
    t2.start()
    time.sleep(0.05)
    base_url2 = f"http://127.0.0.1:{port2}"

    # Query active session
    resp = httpx.get(f"{base_url2}/api/session", headers=headers)
    assert resp.status_code == 200
    restored = resp.json()

    # Assert all state survived restart exactly
    assert restored["repo_name"] == temp_git_repo.name
    assert restored["intention"] == "Fix mobile login redirect and dashboard"
    assert restored["criteria"] == ["Mobile navigation at 390px", "Auth tests pass"]
    assert restored["restart_note"] == custom_restart_note
    assert restored["is_note_user_edited"] == 1

    # Assert finding lifecycle decisions survived restart
    restored_findings = {f["finding_id"]: f for f in restored["findings"]}
    f1_restored = restored_findings["fnd-login-redirect"]
    assert f1_restored["status"] == "user-reported-resolved"
    assert (
        f1_restored["user_reason"]
        == "Verified manually in Chrome mobile emulator at 390px"
    )

    f2_restored = restored_findings["fnd-readme-stale"]
    assert f2_restored["status"] == "deferred"
    assert f2_restored["user_reason"] == "Doc updates deferred until PR review"

    # Clean shutdown of server 2
    httpx.post(f"{base_url2}/api/shutdown", headers=headers)
    t2.join(timeout=2.0)
    server2.server_close()
