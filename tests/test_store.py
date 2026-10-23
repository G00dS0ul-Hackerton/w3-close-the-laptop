"""Tests for SteadyDev SQLite persistence store (Milestone M3)."""

import sqlite3
from pathlib import Path

import pytest

from steadydev.models import Finding, FindingCategory, FindingStatus
from steadydev.store import SessionStore


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    db_file = tmp_path / "steadydev_test.db"
    return SessionStore(db_path=db_file)


def test_schema_migration_and_pragmas(store: SessionStore, tmp_path: Path) -> None:
    """Verify database initializes with WAL mode, foreign keys, and user_version = 4."""
    with store.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        version = cursor.fetchone()[0]
        assert version == 4

        cursor.execute("PRAGMA foreign_keys;")
        foreign_keys = cursor.fetchone()[0]
        assert foreign_keys == 1

        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode.lower() == "wal"


def test_app_settings_key_value(store: SessionStore) -> None:
    """Verify get_setting and set_setting operations on app_settings table."""
    assert store.get_setting("non_existent") is None
    assert store.get_setting("non_existent", default="fallback") == "fallback"

    store.set_setting("telemetry_enabled", "true")
    assert store.get_setting("telemetry_enabled") == "true"

    # Update value
    store.set_setting("telemetry_enabled", "false")
    assert store.get_setting("telemetry_enabled") == "false"


def test_get_or_create_session(store: SessionStore, tmp_path: Path) -> None:
    """Verify session creation and idempotent retrieval for a repo path."""
    repo_dir = tmp_path / "my_project"
    repo_dir.mkdir()

    session1 = store.get_or_create_session(
        repo_path=str(repo_dir), repo_name="my_project"
    )
    assert session1["repo_name"] == "my_project"
    assert session1["is_ended"] == 0
    assert session1["is_note_user_edited"] == 0
    assert (
        "Open the dashboard" in session1["restart_note"]
        or len(session1["restart_note"]) > 0
    )

    # Retrieve existing
    session2 = store.get_or_create_session(
        repo_path=str(repo_dir), repo_name="my_project"
    )
    assert session2["session_id"] == session1["session_id"]


def test_restart_note_preservation(store: SessionStore, tmp_path: Path) -> None:
    """Verify user-edited restart note survives and sets edit flag."""
    repo_dir = tmp_path / "my_project"
    repo_dir.mkdir()
    session = store.get_or_create_session(
        repo_path=str(repo_dir), repo_name="my_project"
    )

    custom_note = "Verify mobile navigation at 390px tomorrow morning."
    store.save_restart_note(
        session["session_id"], note_text=custom_note, is_user_edited=True
    )

    updated = store.get_session_by_id(session["session_id"])
    assert updated["restart_note"] == custom_note
    assert updated["is_note_user_edited"] == 1


def test_update_session_intention_and_criteria(
    store: SessionStore, tmp_path: Path
) -> None:
    """Verify updating session intention and criteria."""
    repo_dir = tmp_path / "my_project"
    repo_dir.mkdir()
    session = store.get_or_create_session(
        repo_path=str(repo_dir), repo_name="my_project"
    )

    new_intention = "Refactor token authentication"
    new_criteria = ["Criterion 1: Auth passes", "Criterion 2: No regressions"]
    store.update_session_intention(
        session["session_id"], intention=new_intention, criteria=new_criteria
    )

    updated = store.get_session_by_id(session["session_id"])
    assert updated["intention"] == new_intention
    assert updated["criteria"] == new_criteria


def test_save_snapshot_and_findings(store: SessionStore, tmp_path: Path) -> None:
    """Verify saving snapshots, receipts, and findings."""
    repo_dir = tmp_path / "my_project"
    repo_dir.mkdir()
    session = store.get_or_create_session(
        repo_path=str(repo_dir), repo_name="my_project"
    )

    snapshot_id = store.save_snapshot(
        session_id=session["session_id"],
        git_head_sha="abcdef1234567890",
        diff_hash="diffhash123",
        untracked_hash="untrackedhash123",
        composite_hash="composite123",
    )
    assert snapshot_id is not None

    finding = Finding(
        finding_id="fnd-test-01",
        category=FindingCategory.EVIDENCE_MISMATCH,
        locator="src/auth.py:42",
        description="Missing test coverage for auth edge case",
        evidence="Receipt shows no tests executed",
        status=FindingStatus.OPEN,
    )
    store.save_findings(
        session_id=session["session_id"], snapshot_id=snapshot_id, findings=[finding]
    )

    active_findings = store.get_findings(session_id=session["session_id"])
    assert len(active_findings) == 1
    assert active_findings[0]["finding_id"] == "fnd-test-01"
    assert active_findings[0]["status"] == "open"


def test_update_finding_lifecycle(store: SessionStore, tmp_path: Path) -> None:
    """Verify user resolution and explicit deferral lifecycle state transitions."""
    repo_dir = tmp_path / "my_project"
    repo_dir.mkdir()
    session = store.get_or_create_session(
        repo_path=str(repo_dir), repo_name="my_project"
    )

    snapshot_id = store.save_snapshot(
        session_id=session["session_id"],
        git_head_sha="abcdef1234567890",
        diff_hash="diff1",
        untracked_hash="untracked1",
        composite_hash="comp1",
    )

    f1 = Finding(
        finding_id="fnd-01",
        category=FindingCategory.UNVERIFIED,
        locator="src/login.py:10",
        description="Login redirect needs mobile test",
        status=FindingStatus.OPEN,
    )
    store.save_findings(
        session_id=session["session_id"], snapshot_id=snapshot_id, findings=[f1]
    )

    # User resolves with reason
    store.update_finding_status(
        finding_id="fnd-01",
        status="user-reported-resolved",
        user_reason="Verified manually in Chrome mobile viewport",
    )

    f_res = store.get_finding_by_id("fnd-01")
    assert f_res["status"] == "user-reported-resolved"
    assert f_res["user_reason"] == "Verified manually in Chrome mobile viewport"

    # Evidence retired
    store.update_finding_status(
        finding_id="fnd-01",
        status="evidence-retired",
        retired_by_receipt_id="rcpt-999",
    )
    f_ret = store.get_finding_by_id("fnd-01")
    assert f_ret["status"] == "evidence-retired"
    assert f_ret["retired_by_receipt_id"] == "rcpt-999"


def test_close_session(store: SessionStore, tmp_path: Path) -> None:
    """Verify session closing marks is_ended and saves summary."""
    repo_dir = tmp_path / "my_project"
    repo_dir.mkdir()
    session = store.get_or_create_session(
        repo_path=str(repo_dir), repo_name="my_project"
    )

    store.close_session(
        session_id=session["session_id"],
        closing_summary={"unresolved_findings": 1, "passing_receipts": 2},
    )

    closed = store.get_session_by_id(session["session_id"])
    assert closed["is_ended"] == 1
    assert closed["closing_summary_json"] is not None


def test_transaction_rollback_on_failure(store: SessionStore, tmp_path: Path) -> None:
    """Verify atomic transaction rolls back on error and does not commit partial data."""
    repo_dir = tmp_path / "my_project"
    repo_dir.mkdir()
    session = store.get_or_create_session(
        repo_path=str(repo_dir), repo_name="my_project"
    )

    with pytest.raises(sqlite3.IntegrityError), store.transaction() as conn:
        # Insert valid snapshot
        conn.execute(
            "INSERT INTO snapshots (snapshot_id, session_id, git_head_sha, diff_hash, untracked_hash, composite_hash, created_at) "
            "VALUES ('snap-valid', ?, 'sha', 'diff', 'untracked', 'comp', 'now')",
            (session["session_id"],),
        )
        # Insert invalid finding referencing non-existent snapshot to trigger FOREIGN KEY failure
        conn.execute(
            "INSERT INTO findings (finding_id, session_id, snapshot_id, category, title, detail, file_path, status, created_at, updated_at) "
            "VALUES ('fnd-invalid', ?, 'non-existent-snapshot', 'cat', 'title', 'detail', 'path', 'open', 'now', 'now')",
            (session["session_id"],),
        )

    # Verify snap-valid was rolled back
    with store.get_connection() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM snapshots WHERE snapshot_id = 'snap-valid'"
        )
        assert cursor.fetchone()[0] == 0


def test_checkpoint_truncate(store: SessionStore) -> None:
    """Verify WAL checkpoint truncate executes without exception."""
    store.checkpoint(mode="TRUNCATE")


def test_multi_repo_session_isolation(store: SessionStore, tmp_path: Path) -> None:
    """Verify repo A and repo B maintain separate sessions and distinct paths."""
    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    repo_a.mkdir()
    repo_b.mkdir()

    sess_a = store.get_or_create_session(str(repo_a), "repo_a")
    sess_b = store.get_or_create_session(str(repo_b), "repo_b")

    assert sess_a["session_id"] != sess_b["session_id"]
    assert sess_a["repo_path"] != sess_b["repo_path"]

    # Switching back to repo A returns sess_a without affecting sess_b
    sess_a2 = store.get_or_create_session(str(repo_a), "repo_a")
    assert sess_a2["session_id"] == sess_a["session_id"]


def test_multi_repo_finding_collision_resilience(
    store: SessionStore, tmp_path: Path
) -> None:
    """Verify findings with identical finding_id in repo A and repo B do not collide."""
    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    repo_a.mkdir()
    repo_b.mkdir()

    sess_a = store.get_or_create_session(str(repo_a), "repo_a")
    sess_b = store.get_or_create_session(str(repo_b), "repo_b")

    snap_a = store.save_snapshot(sess_a["session_id"], "shaA", "d", "u", "cA")
    snap_b = store.save_snapshot(sess_b["session_id"], "shaB", "d", "u", "cB")

    f_common = Finding(
        finding_id="fnd-shared-locator",
        category=FindingCategory.UNVERIFIED,
        locator="src/index.ts:1",
        description="Check shared path",
    )

    # Save to repo A
    store.save_findings(sess_a["session_id"], snap_a, [f_common])
    assert len(store.get_findings(sess_a["session_id"])) == 1

    # Save to repo B must succeed and not raise IntegrityError or overwrite repo A
    store.save_findings(sess_b["session_id"], snap_b, [f_common])
    assert len(store.get_findings(sess_b["session_id"])) == 1
    assert len(store.get_findings(sess_a["session_id"])) == 1


def test_cross_session_finding_status_isolation(
    store: SessionStore, tmp_path: Path
) -> None:
    """Verify that updating a finding's status in session A does not mutate the same finding ID in session B."""
    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    repo_a.mkdir()
    repo_b.mkdir()

    sess_a = store.get_or_create_session(str(repo_a), "repo_a")
    sess_b = store.get_or_create_session(str(repo_b), "repo_b")

    snap_a = store.save_snapshot(sess_a["session_id"], "shaA", "d", "u", "cA")
    snap_b = store.save_snapshot(sess_b["session_id"], "shaB", "d", "u", "cB")

    f_shared = Finding(
        finding_id="fnd-cross-session",
        category=FindingCategory.UNVERIFIED,
        locator="src/shared.py:1",
        description="Shared check",
        status=FindingStatus.OPEN,
    )

    store.save_findings(sess_a["session_id"], snap_a, [f_shared])
    store.save_findings(sess_b["session_id"], snap_b, [f_shared])

    # Update in session A only, passing session_id
    store.update_finding_status(
        finding_id="fnd-cross-session",
        status="user-reported-resolved",
        user_reason="Resolved in session A",
        session_id=sess_a["session_id"],
    )

    findings_a = store.get_findings(sess_a["session_id"])
    findings_b = store.get_findings(sess_b["session_id"])

    assert findings_a[0]["status"] == "user-reported-resolved"
    assert findings_b[0]["status"] == "open", "Session B's finding must remain OPEN"


def test_multi_repo_receipt_isolation(store: SessionStore, tmp_path: Path) -> None:
    """Verify check receipts in repo B do not overwrite receipts in repo A."""
    from steadydev.models import CheckReceipt

    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    repo_a.mkdir()
    repo_b.mkdir()

    sess_a = store.get_or_create_session(str(repo_a), "repo_a")
    sess_b = store.get_or_create_session(str(repo_b), "repo_b")
    snap_a = store.save_snapshot(sess_a["session_id"], "shaA", "d", "u", "cA")
    snap_b = store.save_snapshot(sess_b["session_id"], "shaB", "d", "u", "cB")

    rcpt_a = CheckReceipt(
        receipt_id="r1",
        command="pytest",
        exit_code=0,
        output_summary="pass",
        timestamp_utc="2026-10-21T00:00:00Z",
    )
    store.save_receipts(sess_a["session_id"], snap_a, [rcpt_a])
    assert len(store.get_receipts(sess_a["session_id"])) == 1

    rcpt_b = CheckReceipt(
        receipt_id="r1",
        command="cargo test",
        exit_code=0,
        output_summary="pass",
        timestamp_utc="2026-10-21T00:00:00Z",
    )
    store.save_receipts(sess_b["session_id"], snap_b, [rcpt_b])

    # Repo A must still retain its receipt without being overwritten
    assert len(store.get_receipts(sess_a["session_id"])) == 1
    assert store.get_receipts(sess_a["session_id"])[0]["command"] == "pytest"
    assert store.get_receipts(sess_b["session_id"])[0]["command"] == "cargo test"


def test_reopen_and_fresh_session_lifecycle(
    store: SessionStore, tmp_path: Path
) -> None:
    """Verify closing a session allows starting a fresh session instead of being trapped."""
    repo = tmp_path / "repo_lifecycle"
    repo.mkdir()

    s1 = store.get_or_create_session(str(repo), "repo_lifecycle")
    store.close_session(s1["session_id"], {"left_here": True})

    # Active session should now be None because s1 is ended
    active = store.get_active_session(str(repo))
    assert active is None

    # Starting fresh session succeeds
    s2 = store.create_fresh_session(
        str(repo), "repo_lifecycle", "Day 2 goal", ["Criterion 1"]
    )
    assert s2["session_id"] != s1["session_id"]
    assert s2["is_ended"] == 0

    # get_active_session now returns s2
    active2 = store.get_active_session(str(repo))
    assert active2 is not None
    assert active2["session_id"] == s2["session_id"]


def test_empty_state_detection_and_recent_repos(
    store: SessionStore, tmp_path: Path
) -> None:
    """Verify empty state summary for uninitiated repo vs active repo and recent repo listing."""
    repo = tmp_path / "repo_empty"
    repo.mkdir()

    summary_pre = store.get_repo_state_summary(str(repo))
    assert summary_pre["state"] == "no_prior_sessions"
    assert summary_pre["session_count"] == 0

    store.get_or_create_session(str(repo), "repo_empty")
    summary_post = store.get_repo_state_summary(str(repo))
    assert summary_post["state"] == "active"
    assert summary_post["is_empty_snapshot"] is True
    assert summary_post["finding_count"] == 0

    recents = store.list_recent_repositories()
    assert any(r["repo_name"] == "repo_empty" for r in recents)


def test_reset_session_archives_active_and_creates_fresh(
    store: SessionStore, tmp_path: Path
) -> None:
    """Verify reset_session archives previous active session and starts a clean session."""
    repo = tmp_path / "repo_reset"
    repo.mkdir()

    s1 = store.get_or_create_session(str(repo), "repo_reset")
    snap_id = store.save_snapshot(s1["session_id"], "head", "diff", "untracked", "comp")
    f1 = Finding(
        finding_id="f-1",
        category=FindingCategory.UNVERIFIED,
        locator="src/test.py:1",
        description="Unverified",
        evidence="None",
        status=FindingStatus.OPEN,
    )
    store.save_findings(s1["session_id"], snap_id, [f1])
    store.update_finding_status(
        "f-1",
        "deferred",
        user_reason="Will check tomorrow",
        session_id=s1["session_id"],
    )

    s2 = store.reset_session(str(repo), "repo_reset")
    assert s2["session_id"] != s1["session_id"]
    assert s2["is_ended"] == 0

    # Old session is now ended
    s1_reloaded = store.get_session_by_id(s1["session_id"])
    assert s1_reloaded is not None
    assert s1_reloaded["is_ended"] == 1

    # Findings in new session are empty
    new_findings = store.get_findings(s2["session_id"])
    assert len(new_findings) == 0

    # Findings in old session remain intact in SQLite
    old_findings = store.get_findings(s1["session_id"])
    assert len(old_findings) == 1
    assert old_findings[0]["status"] == "deferred"
    assert old_findings[0]["user_reason"] == "Will check tomorrow"
