"""Live repository Git snapshot collector, path canonicalization, and safe exclusion."""

import subprocess
from pathlib import Path

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


def collect_review_packet_from_git(
    repo_path: str | Path,
    session_intention: str,
    acceptance_criteria: list[str],
    check_receipts: list[CheckReceipt],
    prior_findings: list[Finding] | None = None,
    explicit_deferrals: list[str] | None = None,
    max_files: int = 6,
) -> ReviewPacket:
    """Build a complete, sanitized ReviewPacket from a live Git repository."""
    root = validate_repo_root(repo_path)
    changed, omitted_git, git_truncated = collect_git_snapshot(root)

    packet = build_review_packet(
        session_intention=session_intention,
        acceptance_criteria=acceptance_criteria,
        changed_files=changed,
        check_receipts=check_receipts,
        prior_findings=prior_findings,
        explicit_deferrals=explicit_deferrals,
        repo_name=root.name,
        max_files=max_files,
    )

    # Combine git-level omitted files and truncation flags
    if omitted_git:
        packet.omitted_files.extend(
            [f for f in omitted_git if f not in packet.omitted_files]
        )
    if git_truncated:
        packet.truncated = True

    return packet
