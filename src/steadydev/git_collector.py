"""Live repository Git snapshot collector, path canonicalization, and safe exclusion."""

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

from steadydev.models import ChangedFile, CheckReceipt, Finding, ReviewPacket
from steadydev.packet import build_review_packet, is_allowlisted


def validate_repo_root(repo_path: str | Path) -> Path:
    """Canonicalize repository root path and verify it is a valid Git repository."""
    try:
        root = Path(repo_path).resolve(strict=True)
    except FileNotFoundError:
        raise NotADirectoryError(f"Target repository does not exist: {repo_path}")
    if not root.is_dir():
        raise NotADirectoryError(f"Target repository is not a directory: {root}")
    if not (root / ".git").exists():
        raise ValueError(f"Target directory is not a Git repository: {root}")
    return root


def validate_candidate_repo(
    repo_path: str | Path,
) -> tuple[bool, Path | None, str | None]:
    """Validate candidate repository path for dynamic switching with system root guards."""
    try:
        candidate = Path(repo_path).resolve(strict=True)
    except FileNotFoundError:
        return False, None, f"Directory does not exist: {repo_path}"
    except (OSError, ValueError) as e:
        return False, None, f"Invalid path: {e}"

    if not candidate.is_dir():
        return False, None, f"Path is not a directory: {candidate}"

    # Guard 1: Root directory (e.g. C:\ or /)
    if candidate == candidate.parent:
        return False, None, "Selecting filesystem drive root is forbidden"

    # Guard 2: Windows SystemRoot
    sys_root = os.environ.get("SystemRoot")
    if sys_root and candidate == Path(sys_root).resolve():
        return False, None, "Selecting system directory is forbidden"

    # Guard 3: User home directory
    try:
        home_dir = Path.home().resolve()
        if candidate == home_dir:
            return False, None, "Selecting user home root is forbidden"
    except (RuntimeError, OSError):
        home_dir = None

    # Guard 4: .git existence
    if not (candidate / ".git").exists():
        return False, None, "Target directory is not a Git repository (.git missing)"

    # Guard 5: verify top-level repository
    proc = _run_git_cmd(candidate, ["rev-parse", "--show-toplevel"])
    if proc.returncode != 0:
        return False, None, "Git verification failed"

    top_level = Path(proc.stdout.strip()).resolve()
    if top_level != candidate:
        return (
            False,
            None,
            f"Directory is a subfolder of Git repository '{top_level.name}', not the repository root",
        )

    return True, candidate, None


def validate_repo_relative_path(repo_root: Path, file_candidate: str | Path) -> str:
    """Validate that candidate file is strictly contained within repo boundary without traversal."""
    raw = str(file_candidate).replace("\\", "/")
    parts = [p for p in raw.split("/") if p]
    if ".." in parts:
        raise PermissionError(f"Directory traversal detected: {file_candidate}")

    target = (repo_root / file_candidate).resolve()
    if not target.is_relative_to(repo_root):
        raise PermissionError(f"Path outside repository boundary: {file_candidate}")

    return target.relative_to(repo_root).as_posix()


def _run_git_cmd(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Execute read-only git command strictly within repo root without shell execution."""
    cmd = ["git", "-c", "core.quotepath=false"] + args
    return subprocess.run(
        cmd,
        cwd=str(repo_root),
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _split_unified_diff(raw_diff: str) -> dict[str, str]:
    """Split unified diff output into mapping of relative_path -> file_diff."""
    file_diffs: dict[str, str] = {}
    current_path: str | None = None
    current_lines: list[str] = []

    for line in raw_diff.splitlines():
        if line.startswith("diff --git "):
            if current_path and current_lines:
                file_diffs[current_path] = "\n".join(current_lines)
            tokens = line.split()
            # diff --git a/path b/path
            if len(tokens) >= 4 and tokens[3].startswith("b/"):
                current_path = tokens[3][2:]
            else:
                current_path = None
            current_lines = [line]
        elif current_path is not None:
            current_lines.append(line)

    if current_path and current_lines:
        file_diffs[current_path] = "\n".join(current_lines)

    return file_diffs


def collect_git_snapshot(
    repo_root: str | Path,
    max_untracked_file_bytes: int = 32768,
) -> tuple[list[ChangedFile], list[str], bool]:
    """Collect bounded staged, unstaged, and untracked changes from live git repository."""
    root = validate_repo_root(repo_root)
    changed_files: list[ChangedFile] = []
    omitted_files: list[str] = []
    truncated = False

    # Check if HEAD exists
    rev_check = _run_git_cmd(root, ["rev-parse", "--verify", "HEAD"])
    has_head = rev_check.returncode == 0

    # Collect tracked changes via git diff
    if has_head:
        diff_proc = _run_git_cmd(
            root,
            [
                "--no-pager",
                "diff",
                "--no-color",
                "--no-ext-diff",
                "--unified=3",
                "HEAD",
            ],
        )
    else:
        diff_proc = _run_git_cmd(
            root,
            [
                "--no-pager",
                "diff",
                "--no-color",
                "--no-ext-diff",
                "--cached",
                "--unified=3",
            ],
        )

    raw_diff = diff_proc.stdout.replace("\r\n", "\n")
    tracked_diffs = _split_unified_diff(raw_diff)

    for path, diff_content in tracked_diffs.items():
        try:
            rel_path = validate_repo_relative_path(root, path)
        except PermissionError:
            omitted_files.append(path)
            continue

        if not is_allowlisted(rel_path):
            omitted_files.append(rel_path)
            continue

        changed_files.append(
            ChangedFile(
                path=rel_path,
                status="modified",
                diff=diff_content,
            )
        )

    # Collect untracked files via status porcelain
    status_proc = _run_git_cmd(root, ["status", "--porcelain=v1", "-uall"])
    status_lines = status_proc.stdout.splitlines()

    for line in status_lines:
        if not line.startswith("?? "):
            continue
        rel_candidate = line[3:].strip()
        # Strip quotes if git returned quoted path
        if rel_candidate.startswith('"') and rel_candidate.endswith('"'):
            rel_candidate = rel_candidate[1:-1]

        try:
            rel_path = validate_repo_relative_path(root, rel_candidate)
        except PermissionError:
            omitted_files.append(rel_candidate)
            continue

        if not is_allowlisted(rel_path):
            omitted_files.append(rel_path)
            continue

        full_path = root / rel_path
        if not full_path.is_file():
            continue

        file_stat = full_path.stat()
        if file_stat.st_size > max_untracked_file_bytes:
            omitted_files.append(
                f"{rel_path} (exceeds size limit {max_untracked_file_bytes}B)"
            )
            truncated = True
            continue

        # Binary check (first 1024 bytes)
        try:
            with open(full_path, "rb") as bf:
                chunk = bf.read(1024)
                if b"\x00" in chunk:
                    omitted_files.append(f"{rel_path} (binary file)")
                    continue
            with open(full_path, "r", encoding="utf-8", errors="replace") as tf:
                content = tf.read().replace("\r\n", "\n")
        except (OSError, UnicodeError):
            omitted_files.append(f"{rel_path} (read error)")
            continue

        line_count = len(content.splitlines())
        synthetic_diff = (
            f"diff --git a/{rel_path} b/{rel_path}\n"
            f"new file mode 10644\n"
            f"--- /dev/null\n"
            f"+++ b/{rel_path}\n"
            f"@@ -0,0 +1,{line_count} @@\n"
            + "".join(f"+{l}\n" for l in content.splitlines())
        )

        changed_files.append(
            ChangedFile(
                path=rel_path,
                status="added",
                diff=synthetic_diff.strip(),
            )
        )

    return changed_files, omitted_files, truncated


def get_git_status_summary(
    repo_root: str | Path,
    changed_files: list[ChangedFile] | None = None,
    omitted_files: list[str] | None = None,
) -> dict[str, Any]:
    """Compute structured git status summary including state, head_sha, branch, and commit status."""
    root = validate_repo_root(repo_root)

    # 1. Branch name
    branch_proc = _run_git_cmd(root, ["branch", "--show-current"])
    branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""

    # 2. HEAD commit
    rev_check = _run_git_cmd(root, ["rev-parse", "--verify", "HEAD"])
    has_commits = rev_check.returncode == 0
    head_sha = rev_check.stdout.strip() if has_commits else "0" * 40

    if changed_files is None or omitted_files is None:
        changed, omitted, _ = collect_git_snapshot(root)
    else:
        changed = changed_files
        omitted = omitted_files

    # 3. Determine high-level state
    if not has_commits:
        state = "no_commits"
    elif not changed and not omitted:
        state = "clean"
    elif not changed and omitted:
        state = "all_omitted"
    else:
        state = "dirty"

    return {
        "state": state,
        "has_commits": has_commits,
        "head_sha": head_sha,
        "branch": branch,
        "changed_files_count": len(changed),
        "omitted_files_count": len(omitted),
    }


def compute_snapshot_fingerprint(
    repo_root: str | Path,
) -> tuple[str, str, str, str]:
    """Compute deterministic Git HEAD SHA, diff hash, untracked hash, and 16-hex composite hash."""
    root = validate_repo_root(repo_root)

    # 1. Git HEAD SHA
    rev_proc = _run_git_cmd(root, ["rev-parse", "HEAD"])
    if rev_proc.returncode == 0 and rev_proc.stdout.strip():
        head_sha = rev_proc.stdout.strip()
    else:
        head_sha = "0" * 40

    # 2. Tracked diff hash
    if head_sha != "0" * 40:
        diff_proc = _run_git_cmd(
            root, ["--no-pager", "diff", "--no-color", "--no-ext-diff", "HEAD"]
        )
    else:
        diff_proc = _run_git_cmd(
            root, ["--no-pager", "diff", "--no-color", "--no-ext-diff", "--cached"]
        )
    diff_hash = hashlib.sha256(diff_proc.stdout.encode("utf-8")).hexdigest()

    # 3. Untracked files hash
    status_proc = _run_git_cmd(root, ["status", "--porcelain=v1", "-uall"])
    untracked_lines = sorted(
        [
            line[3:].strip()
            for line in status_proc.stdout.splitlines()
            if line.startswith("?? ")
        ]
    )
    untracked_hash = hashlib.sha256(
        "\n".join(untracked_lines).encode("utf-8")
    ).hexdigest()

    # 4. Composite hash (16 chars)
    composite_raw = f"{head_sha}:{diff_hash}:{untracked_hash}".encode()
    composite_hash = hashlib.sha256(composite_raw).hexdigest()[:16]

    return head_sha, diff_hash, untracked_hash, composite_hash


def check_locator_staleness(
    repo_root: str | Path, locators: list[str]
) -> dict[str, tuple[bool, str | None]]:
    """Verify whether files cited in locators physically exist on disk in repo_root.

    Returns mapping of locator -> (is_stale, stale_reason).
    """
    root = validate_repo_root(repo_root)
    results: dict[str, tuple[bool, str | None]] = {}

    for loc in locators:
        if not loc:
            results[loc] = (True, "Empty locator")
            continue
        parts = loc.split(":")
        file_path = parts[0].strip().replace("\\", "/")
        try:
            full_path = (root / file_path).resolve()
            if not full_path.is_relative_to(root):
                results[loc] = (
                    True,
                    f"Locator path outside repository boundary: {file_path}",
                )
            elif not full_path.exists():
                results[loc] = (
                    True,
                    f"File '{file_path}' was deleted or moved from disk",
                )
            else:
                results[loc] = (False, None)
        except (OSError, ValueError) as e:
            results[loc] = (True, f"Locator validation error: {e}")

    return results


def collect_review_packet_from_git(
    repo_path: str | Path,
    session_intention: str,
    acceptance_criteria: list[str],
    check_receipts: list[CheckReceipt],
    prior_findings: list[Finding] | None = None,
    explicit_deferrals: list[str] | None = None,
    max_files: int = 6,
    max_aggregate_diff_bytes: int = 12288,
) -> ReviewPacket:
    """Build a complete, sanitized ReviewPacket from a live Git repository."""
    root = validate_repo_root(repo_path)
    changed, omitted_git, git_truncated = collect_git_snapshot(root)
    head_sha, _diff_h, _untracked_h, composite_h = compute_snapshot_fingerprint(root)

    packet = build_review_packet(
        session_intention=session_intention,
        acceptance_criteria=acceptance_criteria,
        changed_files=changed,
        check_receipts=check_receipts,
        prior_findings=prior_findings,
        explicit_deferrals=explicit_deferrals,
        repo_name=root.name,
        max_files=max_files,
        max_aggregate_diff_bytes=max_aggregate_diff_bytes,
    )

    packet.snapshot_hash = composite_h
    packet.git_head_sha = head_sha

    # Combine git-level omitted files and truncation flags
    if omitted_git:
        packet.omitted_files.extend(
            [f for f in omitted_git if f not in packet.omitted_files]
        )
    if git_truncated:
        packet.truncated = True

    return packet
