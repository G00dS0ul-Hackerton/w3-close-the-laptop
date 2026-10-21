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
