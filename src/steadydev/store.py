"""SQLite persistence engine for SteadyDev sessions and findings (Milestone M3)."""

import json
import os
import sqlite3
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steadydev.models import CheckReceipt, Finding


def get_default_db_path() -> Path:
    """Return the default SQLite database path outside the monitored repository.

    On Windows, uses %LOCALAPPDATA%\\SteadyDev\\steadydev.db.
    On other platforms or fallback, uses ~/.steadydev/steadydev.db.
    """
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data) / "SteadyDev"
    else:
        base = Path.home() / ".steadydev"
    base.mkdir(parents=True, exist_ok=True)
    return base / "steadydev.db"


class SessionStore:
    """Transactional SQLite store for SteadyDev sessions, snapshots, and findings."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            self.db_path = get_default_db_path()
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        """Create and configure a new SQLite connection with required pragmas."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=5.0,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode; transactions managed via with conn
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager yielding a configured connection."""
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for an atomic transaction with automatic commit/rollback."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            yield conn
            conn.execute("COMMIT;")
        except sqlite3.DatabaseError as exc:
            try:
                from steadydev.telemetry import capture_unexpected_exception

                capture_unexpected_exception(exc, {"component": "storage"})
            except Exception:  # noqa: BLE001, S110
                pass
            conn.execute("ROLLBACK;")
            raise
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def _migrate(self) -> None:
        """Apply schema migrations up to the current schema version (V2)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA user_version;")
                current_version = cursor.fetchone()[0]

                if current_version < 1:
                    self._apply_v1_migration(conn)
                    conn.execute("PRAGMA user_version = 1;")

                if current_version < 2:
                    self._apply_v2_migration(conn)
                    conn.execute("PRAGMA user_version = 2;")

                if current_version < 3:
                    self._apply_v3_migration(conn)
                    conn.execute("PRAGMA user_version = 3;")

                if current_version < 4:
                    self._apply_v4_migration(conn)
                    conn.execute("PRAGMA user_version = 4;")
        except sqlite3.DatabaseError as exc:
            try:
                from steadydev.telemetry import capture_unexpected_exception

                capture_unexpected_exception(exc, {"component": "storage"})
            except Exception:  # noqa: BLE001, S110
                pass
            raise

    def _apply_v1_migration(self, conn: sqlite3.Connection) -> None:
        """Create initial tables for sessions, snapshots, findings, and receipts."""
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                repo_path TEXT NOT NULL,
                repo_name TEXT NOT NULL,
                intention TEXT NOT NULL,
                criteria_json TEXT NOT NULL,
                restart_note TEXT NOT NULL,
                is_note_user_edited INTEGER NOT NULL DEFAULT 0,
                quiet_status TEXT NOT NULL DEFAULT 'Ready for checkpoint',
                is_paused INTEGER NOT NULL DEFAULT 0,
                is_ended INTEGER NOT NULL DEFAULT 0,
                closing_summary_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_repo_path ON sessions(repo_path);
            CREATE INDEX IF NOT EXISTS idx_sessions_is_ended ON sessions(is_ended);

            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                git_head_sha TEXT NOT NULL,
                diff_hash TEXT NOT NULL,
                untracked_hash TEXT NOT NULL,
                composite_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_session ON snapshots(session_id);
            CREATE INDEX IF NOT EXISTS idx_snapshots_composite ON snapshots(composite_hash);

            CREATE TABLE IF NOT EXISTS findings (
                finding_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL,
                file_path TEXT NOT NULL,
                line_start INTEGER,
                line_end INTEGER,
                symbol TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                user_reason TEXT,
                retired_by_receipt_id TEXT,
                is_stale INTEGER NOT NULL DEFAULT 0,
                stale_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_findings_session ON findings(session_id);
            CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);

            CREATE TABLE IF NOT EXISTS check_receipts (
                receipt_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
                command TEXT NOT NULL,
                exit_code INTEGER NOT NULL,
                stdout_summary TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_receipts_session ON check_receipts(session_id);
            """
        )

    def _apply_v2_migration(self, conn: sqlite3.Connection) -> None:
        """Migrate findings and check_receipts to composite primary keys scoped by session_id."""
        conn.execute("PRAGMA foreign_keys = OFF;")
        try:
            conn.executescript(
                """
                -- Recreate findings with composite primary key (session_id, finding_id)
                CREATE TABLE IF NOT EXISTS findings_v2 (
                    finding_id TEXT NOT NULL,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_start INTEGER,
                    line_end INTEGER,
                    symbol TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    user_reason TEXT,
                    retired_by_receipt_id TEXT,
                    is_stale INTEGER NOT NULL DEFAULT 0,
                    stale_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, finding_id)
                );

                INSERT OR IGNORE INTO findings_v2 SELECT * FROM findings;
                DROP TABLE findings;
                ALTER TABLE findings_v2 RENAME TO findings;

                CREATE INDEX IF NOT EXISTS idx_findings_session ON findings(session_id);
                CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);

                -- Recreate check_receipts with composite primary key (session_id, receipt_id)
                CREATE TABLE IF NOT EXISTS check_receipts_v2 (
                    receipt_id TEXT NOT NULL,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
                    command TEXT NOT NULL,
                    exit_code INTEGER NOT NULL,
                    stdout_summary TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, receipt_id)
                );

                INSERT OR IGNORE INTO check_receipts_v2 SELECT * FROM check_receipts;
                DROP TABLE check_receipts;
                ALTER TABLE check_receipts_v2 RENAME TO check_receipts;

                CREATE INDEX IF NOT EXISTS idx_receipts_session ON check_receipts(session_id);
                """
            )
        finally:
            conn.execute("PRAGMA foreign_keys = ON;")

    def _apply_v3_migration(self, conn: sqlite3.Connection) -> None:
        """Add engine column to findings table."""
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(findings);")
        cols = {row[1] for row in cursor.fetchall()}
        if "engine" not in cols:
            conn.execute(
                "ALTER TABLE findings ADD COLUMN engine TEXT NOT NULL DEFAULT 'baseline-checklist';"
            )

    def _apply_v4_migration(self, conn: sqlite3.Connection) -> None:
        """Create app_settings key-value table for persistent configuration."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Fetch a persistent setting by key."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_settings WHERE key = ?;", (key,))
            row = cursor.fetchone()
            if row:
                return str(row[0])
            return default

    def set_setting(self, key: str, value: str) -> None:
        """Set a persistent setting by key."""
        now = datetime.now(UTC).isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
                """,
                (key, value, now),
            )

    def get_or_create_session(self, repo_path: str, repo_name: str) -> dict[str, Any]:
        """Return the latest session for this repo, or create a new one."""
        norm_path = str(Path(repo_path).resolve())
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sessions WHERE repo_path = ? ORDER BY created_at DESC LIMIT 1;",
                (norm_path,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_session_dict(row)

        # Create new default session
        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC).isoformat()
        default_intention = (
            "Fix the login redirect and make the dashboard work on mobile."
        )
        default_criteria = json.dumps(
            [
                "Correct destination",
                "Mobile navigation",
                "No auth regressions",
            ]
        )
        default_note = (
            "Open the dashboard at 390px and check mobile navigation. "
            "The login redirect change has sample auth-test evidence."
        )

        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, repo_path, repo_name, intention, criteria_json,
                    restart_note, is_note_user_edited, quiet_status, is_paused,
                    is_ended, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 'Ready for checkpoint', 0, 0, ?, ?);
                """,
                (
                    session_id,
                    norm_path,
                    repo_name,
                    default_intention,
                    default_criteria,
                    default_note,
                    now,
                    now,
                ),
            )

        return self.get_session_by_id(session_id)  # type: ignore

    def get_session_by_id(self, session_id: str) -> dict[str, Any] | None:
        """Fetch session by its ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sessions WHERE session_id = ?;", (session_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_session_dict(row)
        return None

    def get_active_session(self, repo_path: str) -> dict[str, Any] | None:
        """Fetch current open session for a repository path, or None if all are closed."""
        norm_path = str(Path(repo_path).resolve())
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sessions WHERE repo_path = ? AND is_ended = 0 ORDER BY created_at DESC LIMIT 1;",
                (norm_path,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_session_dict(row)
        return None

    def get_latest_session(self, repo_path: str) -> dict[str, Any] | None:
        """Fetch the most recent session for a repository path, even if ended."""
        norm_path = str(Path(repo_path).resolve())
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sessions WHERE repo_path = ? ORDER BY created_at DESC LIMIT 1;",
                (norm_path,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_session_dict(row)
        return None

    def create_fresh_session(
        self,
        repo_path: str,
        repo_name: str,
        intention: str,
        criteria: list[str],
        restart_note: str = "",
    ) -> dict[str, Any]:
        """Start a new active session for a repo, leaving prior closed sessions intact."""
        norm_path = str(Path(repo_path).resolve())
        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC).isoformat()
        criteria_json = json.dumps(criteria)

        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, repo_path, repo_name, intention, criteria_json,
                    restart_note, is_note_user_edited, quiet_status, is_paused,
                    is_ended, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 'Ready for checkpoint', 0, 0, ?, ?);
                """,
                (
                    session_id,
                    norm_path,
                    repo_name,
                    intention,
                    criteria_json,
                    restart_note,
                    now,
                    now,
                ),
            )

        return self.get_session_by_id(session_id)  # type: ignore

    def reset_session(
        self,
        repo_path: str,
        repo_name: str,
        intention: str = "Review current session changes",
        criteria: list[str] | None = None,
    ) -> dict[str, Any]:
        """Archive any active session for this repository and create a clean session."""
        norm_path = str(Path(repo_path).resolve())
        now = datetime.now(UTC).isoformat()
        if criteria is None:
            criteria = []

        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET is_ended = 1, updated_at = ?
                WHERE repo_path = ? AND is_ended = 0;
                """,
                (now, norm_path),
            )

        return self.create_fresh_session(
            repo_path=norm_path,
            repo_name=repo_name,
            intention=intention,
            criteria=criteria,
            restart_note="",
        )

    def list_recent_repositories(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return distinct repositories ordered by most recent activity."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT repo_path, repo_name,
                       MAX(updated_at) as last_active_at,
                       COUNT(session_id) as total_sessions
                FROM sessions
                GROUP BY repo_path, repo_name
                ORDER BY last_active_at DESC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "repo_path": r[0],
                    "repo_name": r[1],
                    "last_active_at": r[2],
                    "total_sessions": r[3],
                }
                for r in rows
            ]

    def get_repo_state_summary(self, repo_path: str) -> dict[str, Any]:
        """Detect whether repo is fresh, has active session, or is empty."""
        norm_path = str(Path(repo_path).resolve())
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM sessions WHERE repo_path = ?;", (norm_path,)
            )
            session_count = cursor.fetchone()[0]
            if session_count == 0:
                return {"state": "no_prior_sessions", "session_count": 0}

            active = self.get_active_session(norm_path)
            if not active:
                return {"state": "all_sessions_closed", "session_count": session_count}

            cursor.execute(
                "SELECT COUNT(*) FROM snapshots WHERE session_id = ?;",
                (active["session_id"],),
            )
            snapshot_count = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM findings WHERE session_id = ?;",
                (active["session_id"],),
            )
            finding_count = cursor.fetchone()[0]

            return {
                "state": "active",
                "session_id": active["session_id"],
                "snapshot_count": snapshot_count,
                "finding_count": finding_count,
                "is_empty_snapshot": snapshot_count == 0,
            }

    def update_session_intention(
        self, session_id: str, intention: str, criteria: list[str]
    ) -> None:
        """Update intention and criteria for a session."""
        now = datetime.now(UTC).isoformat()
        criteria_json = json.dumps(criteria)
        with self.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET intention = ?, criteria_json = ?, updated_at = ? WHERE session_id = ?;",
                (intention, criteria_json, now, session_id),
            )

    def save_restart_note(
        self, session_id: str, note_text: str, is_user_edited: bool = True
    ) -> None:
        """Persist updated restart note and mark user-edited flag."""
        now = datetime.now(UTC).isoformat()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET restart_note = ?, is_note_user_edited = ?, updated_at = ? WHERE session_id = ?;",
                (note_text, 1 if is_user_edited else 0, now, session_id),
            )

    def save_snapshot(
        self,
        session_id: str,
        git_head_sha: str,
        diff_hash: str,
        untracked_hash: str,
        composite_hash: str,
    ) -> str:
        """Record a working-tree snapshot fingerprint in the session."""
        snapshot_id = f"snap-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC).isoformat()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO snapshots (
                    snapshot_id, session_id, git_head_sha, diff_hash, untracked_hash, composite_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    snapshot_id,
                    session_id,
                    git_head_sha,
                    diff_hash,
                    untracked_hash,
                    composite_hash,
                    now,
                ),
            )
        return snapshot_id

    def save_findings(
        self, session_id: str, snapshot_id: str, findings: list[Finding]
    ) -> None:
        """Persist or update findings in SQLite, preserving user lifecycle states."""
        now = datetime.now(UTC).isoformat()
        with self.transaction() as conn:
            for f in findings:
                # Parse locator file path
                file_path = f.locator.split(":")[0] if ":" in f.locator else f.locator
                line_no = None
                if ":" in f.locator:
                    parts = f.locator.split(":")
                    if len(parts) > 1 and parts[1].isdigit():
                        line_no = int(parts[1])

                # Check if finding already exists in this session
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT status, user_reason FROM findings WHERE finding_id = ? AND session_id = ?;",
                    (f.finding_id, session_id),
                )
                existing = cursor.fetchone()

                if existing:
                    existing_status = existing["status"]
                    # If user has resolved, deferred, or dismissed this finding, keep their decision
                    target_status = (
                        existing_status
                        if existing_status
                        in ("user-reported-resolved", "deferred", "dismissed")
                        else (
                            f.status.value
                            if hasattr(f.status, "value")
                            else str(f.status)
                        )
                    )
                    user_reason = existing["user_reason"]

                    conn.execute(
                        """
                        UPDATE findings SET
                            snapshot_id = ?, category = ?, title = ?, detail = ?, file_path = ?,
                            line_start = ?, status = ?, user_reason = ?, engine = ?, updated_at = ?
                        WHERE finding_id = ? AND session_id = ?;
                        """,
                        (
                            snapshot_id,
                            f.category.value
                            if hasattr(f.category, "value")
                            else str(f.category),
                            f.description[:60],
                            f.description,
                            file_path,
                            line_no,
                            target_status,
                            user_reason,
                            getattr(f, "engine", "baseline-checklist")
                            or "baseline-checklist",
                            now,
                            f.finding_id,
                            session_id,
                        ),
                    )
                else:
                    status_val = (
                        f.status.value if hasattr(f.status, "value") else str(f.status)
                    )
                    conn.execute(
                        """
                        INSERT INTO findings (
                            finding_id, session_id, snapshot_id, category, title, detail, file_path,
                            line_start, status, user_reason, engine, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?);
                        """,
                        (
                            f.finding_id,
                            session_id,
                            snapshot_id,
                            f.category.value
                            if hasattr(f.category, "value")
                            else str(f.category),
                            f.description[:60],
                            f.description,
                            file_path,
                            line_no,
                            status_val,
                            getattr(f, "engine", "baseline-checklist")
                            or "baseline-checklist",
                            now,
                            now,
                        ),
                    )

    def get_findings(self, session_id: str) -> list[dict[str, Any]]:
        """Fetch all findings associated with a session."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM findings WHERE session_id = ? ORDER BY created_at ASC;",
                (session_id,),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_finding_by_id(
        self, finding_id: str, session_id: str | None = None
    ) -> dict[str, Any] | None:
        """Fetch a specific finding by ID (optionally scoped to session)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if session_id:
                cursor.execute(
                    "SELECT * FROM findings WHERE finding_id = ? AND session_id = ?;",
                    (finding_id, session_id),
                )
            else:
                cursor.execute(
                    "SELECT * FROM findings WHERE finding_id = ?;", (finding_id,)
                )
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

    def update_finding_status(
        self,
        finding_id: str,
        status: str,
        user_reason: str | None = None,
        retired_by_receipt_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Update lifecycle status and reason/retirement evidence for a finding."""
        now = datetime.now(UTC).isoformat()
        with self.transaction() as conn:
            if session_id:
                conn.execute(
                    """
                    UPDATE findings SET
                        status = ?, user_reason = COALESCE(?, user_reason),
                        retired_by_receipt_id = COALESCE(?, retired_by_receipt_id),
                        updated_at = ?
                    WHERE finding_id = ? AND session_id = ?;
                    """,
                    (
                        status,
                        user_reason,
                        retired_by_receipt_id,
                        now,
                        finding_id,
                        session_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE findings SET
                        status = ?, user_reason = COALESCE(?, user_reason),
                        retired_by_receipt_id = COALESCE(?, retired_by_receipt_id),
                        updated_at = ?
                    WHERE finding_id = ?;
                    """,
                    (status, user_reason, retired_by_receipt_id, now, finding_id),
                )

    def mark_finding_stale(
        self, finding_id: str, is_stale: bool = True, stale_reason: str | None = None
    ) -> None:
        """Mark a finding stale due to locator invalidation (deleted or renamed file)."""
        now = datetime.now(UTC).isoformat()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE findings SET is_stale = ?, stale_reason = ?, updated_at = ? WHERE finding_id = ?;",
                (1 if is_stale else 0, stale_reason, now, finding_id),
            )

    def save_receipts(
        self, session_id: str, snapshot_id: str, receipts: list[CheckReceipt]
    ) -> None:
        """Persist verification check receipts."""
        now = datetime.now(UTC).isoformat()
        with self.transaction() as conn:
            for r in receipts:
                status_str = "passed" if r.exit_code == 0 else "failed"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO check_receipts (
                        receipt_id, session_id, snapshot_id, command, exit_code, stdout_summary, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        r.receipt_id,
                        session_id,
                        snapshot_id,
                        r.command,
                        r.exit_code,
                        r.output_summary,
                        status_str,
                        now,
                    ),
                )

    def get_receipts(self, session_id: str) -> list[dict[str, Any]]:
        """Fetch check receipts for a session."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM check_receipts WHERE session_id = ? ORDER BY created_at ASC;",
                (session_id,),
            )
            return [dict(r) for r in cursor.fetchall()]

    def close_session(
        self, session_id: str, closing_summary: dict[str, Any] | None = None
    ) -> None:
        """Mark a session closed ('Leave it here'), preserving handoff state without committing git."""
        now = datetime.now(UTC).isoformat()
        summary_json = json.dumps(closing_summary) if closing_summary else None
        with self.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET is_ended = 1, closing_summary_json = ?, updated_at = ? WHERE session_id = ?;",
                (summary_json, now, session_id),
            )

    def get_latest_snapshot(self, session_id: str) -> dict[str, Any] | None:
        """Fetch the most recent snapshot record for a session."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT snapshot_id, session_id, git_head_sha, diff_hash, untracked_hash, composite_hash, created_at
                FROM snapshots
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                (session_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def set_session_paused(self, session_id: str, is_paused: bool) -> None:
        """Set paused status for a session."""
        now = datetime.now(UTC).isoformat()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET is_paused = ?, updated_at = ? WHERE session_id = ?;",
                (1 if is_paused else 0, now, session_id),
            )

    def checkpoint(self, mode: str = "TRUNCATE") -> None:
        """Execute a WAL checkpoint to truncate the -wal file on shutdown or cleanup."""
        with self.get_connection() as conn:
            conn.execute(f"PRAGMA wal_checkpoint({mode});")

    def _row_to_session_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert a sqlite3.Row from the sessions table to a dictionary with parsed JSON fields."""
        d = dict(row)
        try:
            d["criteria"] = json.loads(d.get("criteria_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            d["criteria"] = []
        return d
