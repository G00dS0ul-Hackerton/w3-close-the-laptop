"""Unit tests for live Git snapshot collector, path canonicalization, and boundary security."""

from pathlib import Path

import pytest

from steadydev.git_collector import (
    collect_git_snapshot,
    collect_review_packet_from_git,
    validate_repo_relative_path,
    validate_repo_root,
)
from steadydev.models import CheckReceipt


def test_validate_repo_root(temp_git_repo: Path, tmp_path: Path) -> None:
    # Valid git repo
    canonical = validate_repo_root(temp_git_repo)
    assert canonical == temp_git_repo.resolve()

    # Non-git directory
    non_git = tmp_path / "plain_dir"
    non_git.mkdir()
    with pytest.raises(ValueError, match="not a Git repository"):
        validate_repo_root(non_git)

    # Non-existent directory
    with pytest.raises(NotADirectoryError):
        validate_repo_root(tmp_path / "non_existent")


def test_validate_repo_relative_path(temp_git_repo: Path) -> None:
    # Valid relative path
    valid = validate_repo_relative_path(temp_git_repo, "src/main.py")
    assert valid == "src/main.py"

    # Traversal attempt
    with pytest.raises(PermissionError, match="Directory traversal"):
        validate_repo_relative_path(temp_git_repo, "../outside.py")

    with pytest.raises(PermissionError, match="Directory traversal"):
        validate_repo_relative_path(temp_git_repo, "src/../../outside.py")


def test_clean_working_tree(temp_git_repo: Path) -> None:
    changed, omitted, truncated = collect_git_snapshot(temp_git_repo)
    assert changed == []
    assert omitted == []
    assert truncated is False


def test_collect_tracked_and_untracked_changes(temp_git_repo: Path) -> None:
    # Modify tracked file
    readme = temp_git_repo / "README.md"
    readme.write_text("# Mock Project\nUpdated line\nNew section\n", encoding="utf-8")

    # Add untracked allowlisted file
    new_code = temp_git_repo / "src" / "feature.py"
    new_code.parent.mkdir(parents=True)
    new_code.write_text("def hello() -> str:\n    return 'hello'\n", encoding="utf-8")

    # Add untracked secret file (should be omitted)
    secret_env = temp_git_repo / ".env"
    secret_env.write_text("API_SECRET_KEY=supersecret123\n", encoding="utf-8")

    # Add binary file (should be omitted)
    bin_file = temp_git_repo / "data.bin"
    bin_file.write_bytes(b"\x00\x01\x02\x03\x04")

    changed, omitted, _truncated = collect_git_snapshot(temp_git_repo)

    # Check changed files
    paths = [cf.path for cf in changed]
    assert "README.md" in paths
    assert "src/feature.py" in paths
    assert ".env" not in paths
    assert "data.bin" not in paths

    # Check omitted files
    assert any(".env" in om for om in omitted)
    assert any("data.bin" in om for om in omitted)


def test_collect_review_packet_from_git(temp_git_repo: Path) -> None:
    readme = temp_git_repo / "README.md"
    readme.write_text("# Mock Project\nChanged content\n", encoding="utf-8")

    receipt = CheckReceipt(
        receipt_id="rcpt-01",
        command="pytest",
        exit_code=0,
        output_summary="1 passed",
        timestamp_utc="2026-10-21T03:00:00Z",
    )

    packet = collect_review_packet_from_git(
        repo_path=temp_git_repo,
        session_intention="Improve readme",
        acceptance_criteria=["Update documentation"],
        check_receipts=[receipt],
    )

    assert packet.repo_name == temp_git_repo.name
    assert packet.session_intention == "Improve readme"
    assert len(packet.changed_files) == 1
    assert packet.changed_files[0].path == "README.md"
    assert "Changed content" in packet.changed_files[0].diff
