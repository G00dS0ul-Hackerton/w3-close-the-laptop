"""Bounded packet builder, diff truncator, path normalizer, and privacy sanitizer."""

import datetime
import os
import re
import uuid

from steadydev.models import ChangedFile, CheckReceipt, Finding, ReviewPacket

# Excluded directory and file patterns
EXCLUDED_PATTERNS = [
    r"(?:^|[\\/])\.git(?:[\\/]|$)",
    r"(?:^|[\\/])\.venv(?:[\\/]|$)",
    r"(?:^|[\\/])__pycache__(?:[\\/]|$)",
    r"(?:^|[\\/])node_modules(?:[\\/]|$)",
    r"(?:^|[\\/])\.dart_tool(?:[\\/]|$)",
    r"(?:^|[\\/])build(?:[\\/]|$)",
    r"(?:^|[\\/])dist(?:[\\/]|$)",
    r"(?:^|[\\/])\.steadydev(?:[\\/]|$)",
    # SSH keys and cloud credentials
    r"(?:^|[\\/])id_(?:rsa|ed25519|ecdsa|dsa)(?:\.pub)?$",
    r"(?:^|[\\/])credentials\.json$",
    r"(?:^|[\\/])service[-_]account.*\.json$",
    # Certificates and private keys
    r"\.pem$",
    r"\.key$",
    r"\.crt$",
    r"\.pfx$",
    # Database and binary formats
    r"\.sqlite[3]?$",
    r"\.db$",
    r"\.pyc$",
    r"\.exe$",
    r"\.dll$",
    r"\.so$",
    r"\.dylib$",
    r"\.png$",
    r"\.jpg$",
    r"\.jpeg$",
    r"\.gif$",
    r"\.webp$",
    r"\.ico$",
    r"\.pdf$",
    r"\.zip$",
    r"\.tar\.gz$",
    r"\.parquet$",
    r"\.bin$",
    r"\.wasm$",
]

# Secret patterns
SECRET_PATTERNS = [
    r"sk-[a-zA-Z0-9_\-]{20,}",
    r"sk_[a-zA-Z0-9_\-]{20,}",
    r"ghp_[a-zA-Z0-9]{36,}",
    r"github_pat_[a-zA-Z0-9_]{82}",
    r"xi-api-key\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{20,}",
    r"Bearer\s+[a-zA-Z0-9_\-\.]{25,}",
    r"https://[a-f0-9]{32}@[a-z0-9\.\-]+/[0-9]+",  # Sentry DSN
    r"AKIA[0-9A-Z]{16}",  # AWS Key ID
    r"AIza[0-9A-Za-z\-_]{35}",  # Google/Gemini Key
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",  # PEM Key
]

# Sensitive Windows paths and dynamic username tokens (C-2, P-3)
WINDOWS_PATH_VARIANTS = [
    r"[a-zA-Z]:\\\\+Users\\\\+[^\s\\\"'\r\n]+",
    r"[a-zA-Z]:[\\/]+Users[\\/]+[^\s\\/\"'\r\n]+",
    r"C:[\\/]+Users[\\/]+[^\s\\/\"'\r\n]+",
]

_current_user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
_home_user = os.path.basename(os.path.expanduser("~"))

_raw_candidates = {_current_user, _home_user}
_clean_tokens = set()
for c in _raw_candidates:
    if not c:
        continue
    _clean_tokens.add(c)
    # Strip non-ascii / emoji characters to get plain token (e.g. 'JaneDoe' from 'JaneDoe🚀')
    ascii_only = re.sub(r"[^\x20-\x7E]", "", c).strip()
    if len(ascii_only) > 2:
        _clean_tokens.add(ascii_only)
    try:
        from urllib.parse import quote

        quoted = quote(c)
        if quoted != c:
            _clean_tokens.add(quoted)
    except (UnicodeError, ValueError):
        pass

# Check for 8.3 short name on Windows
if os.name == "nt":
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(500)
        home_dir = os.path.expanduser("~")
        if ctypes.windll.kernel32.GetShortPathNameW(home_dir, buf, 500):
            short_base = os.path.basename(buf.value)
            if short_base and len(short_base) > 2:
                _clean_tokens.add(short_base)
    except (OSError, AttributeError):
        pass

USERNAME_TOKENS = sorted(
    [u for u in _clean_tokens if len(u) > 2], key=len, reverse=True
)


def normalize_path(path: str) -> str:
    """Normalize file path to relative path with forward slashes and reject traversal."""
    p = path.replace("\\", "/")
    # Strip drive letters like C:/
    p = re.sub(r"^[a-zA-Z]:/", "", p)
    # Strip leading slashes
    p = p.lstrip("/")
    # Reject traversal tokens
    parts = [part for part in p.split("/") if part]
    if ".." in parts:
        raise ValueError(f"Directory traversal not permitted: {path}")
    return p


def is_allowlisted(path: str) -> bool:
    """Check whether a path is allowed in the bounded review packet."""
    try:
        norm = normalize_path(path)
    except ValueError:
        return False
    base = os.path.basename(norm).lower()

    # Strictly exclude .env and .env.* except .env.example (case-insensitive)
    if base.startswith(".env"):
        return base == ".env.example"

    for pattern in EXCLUDED_PATTERNS:
        if re.search(pattern, norm, re.IGNORECASE):
            return False

    return True


def redact_sensitive_text(text: str) -> str:
    """Redact Windows paths, raw username tokens, and secret keys."""
    redacted = text

    # Redact Windows paths (single and double escaped)
    for pattern in WINDOWS_PATH_VARIANTS:
        redacted = re.sub(pattern, "[USER_HOME]", redacted)

    # Redact username tokens
    for token in USERNAME_TOKENS:
        redacted = redacted.replace(token, "[DEVELOPER_USER]")

    # Redact API keys and secret tokens
    for pattern in SECRET_PATTERNS:
        redacted = re.sub(pattern, "[REDACTED_SECRET]", redacted)

    return redacted


def truncate_diff(
    diff: str, max_lines: int = 250, max_bytes: int = 4096
) -> tuple[str, bool]:
    """Truncate diff hunks to safe line and byte bounds."""
    lines = diff.splitlines()
    truncated = False

    if len(lines) > max_lines:
        omitted = len(lines) - max_lines
        lines = lines[:max_lines]
        lines.append(f"\n[DIFF TRUNCATED: {omitted} lines omitted]")
        truncated = True

    result = "\n".join(lines)
    if len(result.encode("utf-8")) > max_bytes:
        # Byte truncation
        result = result.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
        result += "\n[DIFF TRUNCATED: byte limit exceeded]"
        truncated = True

    return result, truncated


def escape_xml_delimiters(text: str) -> str:
    """Escape XML tags that could break prompt structure."""
    text = text.replace("</git_diff>", "&lt;/git_diff&gt;")
    text = text.replace("</session_intention>", "&lt;/session_intention&gt;")
    text = text.replace("</acceptance_criteria>", "&lt;/acceptance_criteria&gt;")
    text = text.replace("</check_receipts>", "&lt;/check_receipts&gt;")
    text = text.replace("</prior_findings>", "&lt;/prior_findings&gt;")
    text = text.replace("</explicit_deferrals>", "&lt;/explicit_deferrals&gt;")
    text = text.replace("</truncated>", "&lt;/truncated&gt;")
    text = text.replace("</omitted_files>", "&lt;/omitted_files&gt;")
    text = text.replace("</review_context>", "&lt;/review_context&gt;")
    return text


def build_review_packet(
    session_intention: str,
    acceptance_criteria: list[str],
    changed_files: list[ChangedFile],
    check_receipts: list[CheckReceipt],
    prior_findings: list[Finding] | None = None,
    explicit_deferrals: list[str] | None = None,
    repo_name: str = "repo",
    max_files: int = 6,
    max_aggregate_diff_bytes: int = 12288,
) -> ReviewPacket:
    """Construct a clean, sanitized, bounded review packet."""
    packet_id = f"pkt-{uuid.uuid4().hex[:8]}"
    now_utc = datetime.datetime.now(datetime.UTC).isoformat()

    # Allowlist filter
    allowed_files: list[ChangedFile] = []
    omitted_files: list[str] = []
    is_truncated_overall = False

    for cf in changed_files:
        norm_path = normalize_path(cf.path)
        if not is_allowlisted(norm_path):
            omitted_files.append(norm_path)
            continue

        clean_diff = redact_sensitive_text(cf.diff)
        trunc_diff, was_trunc = truncate_diff(clean_diff)
        if was_trunc:
            is_truncated_overall = True

        allowed_files.append(
            ChangedFile(
                path=norm_path,
                status=cf.status,
                diff=trunc_diff,
            )
        )

    # Cap modified files count
    if len(allowed_files) > max_files:
        excess = allowed_files[max_files:]
        allowed_files = allowed_files[:max_files]
        omitted_files.extend([f.path for f in excess])
        is_truncated_overall = True

    # Cap aggregate diff bytes across all allowed files to protect CPU context
    total_bytes = 0
    final_allowed_files: list[ChangedFile] = []
    for af in allowed_files:
        diff_len = len(af.diff.encode("utf-8"))
        if total_bytes + diff_len > max_aggregate_diff_bytes:
            remaining = max(0, max_aggregate_diff_bytes - total_bytes)
            if remaining > 200:
                trunc_bytes = af.diff.encode("utf-8")[:remaining].decode(
                    "utf-8", errors="ignore"
                )
                trunc_bytes += "\n[DIFF TRUNCATED: aggregate packet byte limit reached]"
                final_allowed_files.append(
                    ChangedFile(path=af.path, status=af.status, diff=trunc_bytes)
                )
            else:
                omitted_files.append(af.path)
            is_truncated_overall = True
            break
        else:
            final_allowed_files.append(af)
            total_bytes += diff_len
    allowed_files = final_allowed_files

    # Redact session intention and criteria
    clean_intention = redact_sensitive_text(session_intention)
    clean_criteria = [redact_sensitive_text(c) for c in acceptance_criteria]
    clean_deferrals = [redact_sensitive_text(d) for d in (explicit_deferrals or [])]

    # Redact check receipts
    clean_receipts: list[CheckReceipt] = []
    for r in check_receipts:
        clean_receipts.append(
            CheckReceipt(
                receipt_id=r.receipt_id,
                command=redact_sensitive_text(r.command),
                exit_code=r.exit_code,
                output_summary=redact_sensitive_text(r.output_summary[:500]),
                timestamp_utc=r.timestamp_utc,
            )
        )

    return ReviewPacket(
        packet_id=packet_id,
        timestamp_utc=now_utc,
        repo_name=os.path.basename(normalize_path(repo_name)),
        session_intention=clean_intention,
        acceptance_criteria=clean_criteria,
        changed_files=allowed_files,
        check_receipts=clean_receipts,
        prior_findings=prior_findings or [],
        explicit_deferrals=clean_deferrals,
        truncated=is_truncated_overall,
        omitted_files=omitted_files,
    )


def format_packet_for_prompt(packet: ReviewPacket) -> str:
    """Format review packet into structured XML prompt text with data inertia boundaries."""
    parts = ["<review_context>"]

    parts.append(f"  <repo_name>{escape_xml_delimiters(packet.repo_name)}</repo_name>")
    parts.append(
        f"  <session_intention>\n{escape_xml_delimiters(packet.session_intention)}\n  </session_intention>"
    )

    parts.append("  <acceptance_criteria>")
    for idx, c in enumerate(packet.acceptance_criteria, 1):
        parts.append(
            f'    <criterion index="{idx}">{escape_xml_delimiters(c)}</criterion>'
        )
    parts.append("  </acceptance_criteria>")

    parts.append("  <check_receipts>")
    for r in packet.check_receipts:
        parts.append(
            f'    <receipt id="{r.receipt_id}" command="{escape_xml_delimiters(r.command)}" exit_code="{r.exit_code}" timestamp_utc="{escape_xml_delimiters(r.timestamp_utc)}">\n'
            f"      {escape_xml_delimiters(r.output_summary)}\n"
            f"    </receipt>"
        )
    parts.append("  </check_receipts>")

    parts.append("  <git_diff>")
    for f in packet.changed_files:
        parts.append(
            f'    <file path="{f.path}" status="{f.status}">\n{escape_xml_delimiters(f.diff)}\n    </file>'
        )
    parts.append("  </git_diff>")

    parts.append(f"  <truncated>{str(packet.truncated).lower()}</truncated>")
    if packet.omitted_files:
        parts.append("  <omitted_files>")
        for of in packet.omitted_files:
            parts.append(f"    <file>{escape_xml_delimiters(of)}</file>")
        parts.append("  </omitted_files>")

    if packet.prior_findings:
        parts.append("  <prior_findings>")
        for pf in packet.prior_findings:
            parts.append(
                f'    <finding id="{pf.finding_id}" category="{pf.category.value}" locator="{pf.locator}">\n'
                f"      {escape_xml_delimiters(pf.description)}\n"
                f"    </finding>"
            )
        parts.append("  </prior_findings>")

    if packet.explicit_deferrals:
        parts.append("  <explicit_deferrals>")
        for d in packet.explicit_deferrals:
            parts.append(f"    <deferral>{escape_xml_delimiters(d)}</deferral>")
        parts.append("  </explicit_deferrals>")

    parts.append("</review_context>")
    return "\n".join(parts)
