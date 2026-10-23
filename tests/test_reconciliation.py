"""Tests for snapshot fingerprinting, stable finding IDs, and finding reconciliation (Milestone M3)."""

from pathlib import Path

from steadydev.git_collector import (
    check_locator_staleness,
    collect_review_packet_from_git,
    compute_snapshot_fingerprint,
)
from steadydev.models import (
    Finding,
    FindingCategory,
    FindingStatus,
    compute_finding_id,
)
from steadydev.store import SessionStore


def test_compute_snapshot_fingerprint(temp_git_repo: Path) -> None:
    """Verify deterministic snapshot fingerprint calculation."""
    head_sha, _diff_hash, _untracked_hash, composite_hash = (
        compute_snapshot_fingerprint(temp_git_repo)
    )
    assert len(head_sha) == 40
    assert len(composite_hash) == 16

    # Verify repeatable on clean tree
    _h2, _d2, _u2, c2 = compute_snapshot_fingerprint(temp_git_repo)
    assert composite_hash == c2

    # Modify file and verify fingerprint changes
    readme = temp_git_repo / "README.md"
    readme.write_text("# Mock Project\nModified line\n", encoding="utf-8")
    _, _, _, c_modified = compute_snapshot_fingerprint(temp_git_repo)
    assert c_modified != composite_hash


def test_untracked_content_change_invalidates_fingerprint(temp_git_repo: Path) -> None:
    """Verify that editing the content of an existing untracked file changes the fingerprint."""
    new_untracked = temp_git_repo / "new_feature.py"
    new_untracked.write_text("x = 1\n", encoding="utf-8")

    _h1, _d1, u1, c1 = compute_snapshot_fingerprint(temp_git_repo)

    # Edit the content of the untracked file without renaming or adding new files
    new_untracked.write_text("x = 2\nprint('changed')\n", encoding="utf-8")

    _h2, _d2, u2, c2 = compute_snapshot_fingerprint(temp_git_repo)
    assert u1 != u2, "Untracked hash must change when untracked file content changes"
    assert c1 != c2, "Composite hash must change when untracked file content changes"


def test_stable_content_addressed_finding_ids() -> None:
    """Verify stable, content-addressed IDs are deterministic across runs."""
    id1 = compute_finding_id(
        category=FindingCategory.EVIDENCE_MISMATCH,
        locator="src/auth.py:42",
        anchor="Missing token refresh",
    )
    id2 = compute_finding_id(
        category=FindingCategory.EVIDENCE_MISMATCH,
        locator="src/auth.py:42",
        anchor="Missing token refresh",
    )
    assert id1 == id2
    assert id1.startswith("fnd-")

    # Different locator produces different ID
    id3 = compute_finding_id(
        category=FindingCategory.EVIDENCE_MISMATCH,
        locator="src/auth.py:43",
        anchor="Missing token refresh",
    )
    assert id3 != id1


def test_check_locator_staleness(temp_git_repo: Path) -> None:
    """Verify locator staleness detects deleted or moved files on disk."""
    locators = [
        "README.md:1",
        "src/nonexistent_file.py:10",
    ]
    staleness = check_locator_staleness(temp_git_repo, locators)

    assert staleness["README.md:1"][0] is False
    assert staleness["src/nonexistent_file.py:10"][0] is True
    assert (
        "deleted or moved" in (staleness["src/nonexistent_file.py:10"][1] or "").lower()
    )


def test_user_decision_protection_in_reconciliation(
    temp_git_repo: Path, tmp_path: Path
) -> None:
    """Verify user-reported resolution is not clobbered by new review runs."""
    store = SessionStore(db_path=tmp_path / "test_recon.db")
    session = store.get_or_create_session(
        repo_path=str(temp_git_repo), repo_name=temp_git_repo.name
    )

    # Save initial snapshot and finding
    snap1 = store.save_snapshot(
        session_id=session["session_id"],
        git_head_sha="sha1",
        diff_hash="diff1",
        untracked_hash="u1",
        composite_hash="comp1",
    )

    finding_id = compute_finding_id(
        category=FindingCategory.UNVERIFIED,
        locator="README.md:1",
        anchor="Initial unverified",
    )
    f = Finding(
        finding_id=finding_id,
        category=FindingCategory.UNVERIFIED,
        locator="README.md:1",
        description="Initial unverified item",
        status=FindingStatus.OPEN,
    )
    store.save_findings(
        session_id=session["session_id"], snapshot_id=snap1, findings=[f]
    )

    # User marks it as user-reported-resolved
    store.update_finding_status(
        finding_id=finding_id,
        status="user-reported-resolved",
        user_reason="Manually checked README contents",
    )

    # Next review comes in with same finding still detected as open by baseline or model
    snap2 = store.save_snapshot(
        session_id=session["session_id"],
        git_head_sha="sha2",
        diff_hash="diff2",
        untracked_hash="u2",
        composite_hash="comp2",
    )
    f_incoming = Finding(
        finding_id=finding_id,
        category=FindingCategory.UNVERIFIED,
        locator="README.md:1",
        description="Initial unverified item",
        status=FindingStatus.OPEN,
    )
    store.save_findings(
        session_id=session["session_id"], snapshot_id=snap2, findings=[f_incoming]
    )

    # Assert user decision was preserved
    persisted = store.get_finding_by_id(finding_id)
    assert persisted["status"] == "user-reported-resolved"
    assert persisted["user_reason"] == "Manually checked README contents"


def test_packet_contains_snapshot_fingerprint(temp_git_repo: Path) -> None:
    """Verify collect_review_packet_from_git binds snapshot_hash and git_head_sha."""
    packet = collect_review_packet_from_git(
        repo_path=temp_git_repo,
        session_intention="Check fingerprint binding",
        acceptance_criteria=["Criteria 1"],
        check_receipts=[],
    )
    assert packet.snapshot_hash is not None
    assert len(packet.snapshot_hash) == 16
    assert packet.git_head_sha is not None
    assert len(packet.git_head_sha) == 40
