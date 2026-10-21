"""Shared test fixtures for SteadyDev."""

import subprocess
from pathlib import Path

import pytest

from steadydev.models import (
    ChangedFile,
    CheckReceipt,
    ReviewPacket,
)


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Initialize a disposable local Git repository fixture."""
    repo = tmp_path / "mock_repo"
    repo.mkdir()

    # git init
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "TestUser"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    # Initial commit
    init_file = repo / "README.md"
    init_file.write_text("# Mock Project\nInitial line\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"], cwd=str(repo), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    return repo


@pytest.fixture
def sample_receipt() -> CheckReceipt:
    return CheckReceipt(
        receipt_id="rcpt-001",
        command="pytest -q tests/test_auth.py",
        exit_code=0,
        output_summary="1 passed in 0.05s",
        timestamp_utc="2026-10-21T02:00:00Z",
    )


@pytest.fixture
def sample_changed_file() -> ChangedFile:
    return ChangedFile(
        path="src/auth.py",
        status="modified",
        diff="@@ -10,3 +10,3 @@\n-def login(): return False\n+def login(): return True\n",
    )


@pytest.fixture
def sample_clean_packet(
    sample_receipt: CheckReceipt, sample_changed_file: ChangedFile
) -> ReviewPacket:
    return ReviewPacket(
        packet_id="pkt-test-01",
        timestamp_utc="2026-10-21T02:00:00Z",
        repo_name="sample-repo",
        session_intention="Refactor auth login helper",
        acceptance_criteria=["1. Login returns True", "2. Unit tests pass"],
        changed_files=[sample_changed_file],
        check_receipts=[sample_receipt],
        prior_findings=[],
        explicit_deferrals=[],
    )
