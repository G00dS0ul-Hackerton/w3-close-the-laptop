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
    )
    port = server.server_port
    token = server.token

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.05)  # Yield for server startup

    base_url = f"http://127.0.0.1:{port}"
    yield {"base_url": base_url, "token": token, "repo_root": temp_git_repo}

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
    assert data["active_model"] == "qwen2.5-coder:3b"


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
