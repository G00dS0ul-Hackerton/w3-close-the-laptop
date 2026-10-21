"""Unit tests for bounded packet builder and privacy redaction."""

from steadydev.models import ChangedFile, CheckReceipt
from steadydev.packet import (
    build_review_packet,
    escape_xml_delimiters,
    format_packet_for_prompt,
    is_allowlisted,
    normalize_path,
    redact_sensitive_text,
    truncate_diff,
)


def test_normalize_path() -> None:
    assert (
        normalize_path(r"C:\Users\Project\src\auth.py") == "Users/Project/src/auth.py"
    )
    assert normalize_path(r"src\steadydev\models.py") == "src/steadydev/models.py"
    assert normalize_path("/src/auth.py") == "src/auth.py"


def test_is_allowlisted() -> None:
    # Allowed
    assert is_allowlisted("src/auth.py") is True
    assert is_allowlisted("README.md") is True
    assert is_allowlisted(".env.example") is True

    # Excluded
    assert is_allowlisted(".env") is False
    assert is_allowlisted(".env.local") is False
    assert is_allowlisted(".git/config") is False
    assert is_allowlisted(".venv/lib/site-packages/x.py") is False
    assert is_allowlisted("steadydev.db") is False
    assert is_allowlisted("assets/hero.png") is False
    assert is_allowlisted("binary.exe") is False


def test_redact_sensitive_text() -> None:
    # Single backslash path
    raw1 = r"Traceback: C:\Users\FakeUser\repo\main.py line 12"
    red1 = redact_sensitive_text(raw1)
    assert r"C:\Users" not in red1
    assert "FakeUser" not in red1

    # Escaped JSON backslash path
    raw2 = r'{"path": "C:\\Users\\FakeUser\\repo\\file.py"}'
    red2 = redact_sensitive_text(raw2)
    assert r"C:\\Users" not in red2
    assert "FakeUser" not in red2

    # Secret API key
    raw3 = "Connecting with key sk-dummy-sample-secret-token-abcdef123"
    red3 = redact_sensitive_text(raw3)
    assert "sk-dummy-sample-secret-token-abcdef123" not in red3
    assert "[REDACTED_SECRET]" in red3


def test_truncate_diff() -> None:
    long_diff = "\n".join([f"+line {i}" for i in range(500)])
    truncated, was_trunc = truncate_diff(long_diff, max_lines=50)
    assert was_trunc is True
    assert "[DIFF TRUNCATED: 450 lines omitted]" in truncated
    assert len(truncated.splitlines()) <= 55


def test_escape_xml_delimiters() -> None:
    raw = "Code diff with </git_diff><script>alert(1)</script>"
    escaped = escape_xml_delimiters(raw)
    assert "</git_diff>" not in escaped
    assert "&lt;/git_diff&gt;" in escaped


def test_build_review_packet_omits_excluded_files() -> None:
    files = [
        ChangedFile(path="src/main.py", diff="+x=1\n"),
        ChangedFile(path=".env", diff="SECRET_KEY=12345\n"),
        ChangedFile(path=".git/HEAD", diff="ref: refs/heads/main\n"),
    ]
    receipts = [
        CheckReceipt(
            receipt_id="r1",
            command=r"pytest C:\Users\FakeUser\test.py",
            exit_code=0,
            output_summary="ok",
            timestamp_utc="2026-10-21T02:00:00Z",
        )
    ]
    packet = build_review_packet(
        session_intention="Test session",
        acceptance_criteria=["Pass tests"],
        changed_files=files,
        check_receipts=receipts,
        repo_name="my-repo",
    )
    assert len(packet.changed_files) == 1
    assert packet.changed_files[0].path == "src/main.py"
    assert ".env" in packet.omitted_files
    assert ".git/HEAD" in packet.omitted_files
    # Path redacted in receipts
    assert "FakeUser" not in packet.check_receipts[0].command
    assert "[USER_HOME]" in packet.check_receipts[0].command


def test_format_packet_for_prompt() -> None:
    files = [
        ChangedFile(path="src/main.py", diff="+print('hello')\n"),
        ChangedFile(path=".env", diff="SECRET=1\n"),
    ]
    receipts = [
        CheckReceipt(
            receipt_id="rcpt-01",
            command="pytest",
            exit_code=0,
            output_summary="1 passed",
            timestamp_utc="2026-10-21T02:00:00Z",
        )
    ]
    packet = build_review_packet(
        session_intention="Add greeting",
        acceptance_criteria=["Say hello"],
        changed_files=files,
        check_receipts=receipts,
        repo_name="my-repo",
    )
    prompt_text = format_packet_for_prompt(packet)
    assert "<review_context>" in prompt_text
    assert "<session_intention>" in prompt_text
    assert "Add greeting" in prompt_text
    assert "<git_diff>" in prompt_text
    assert "src/main.py" in prompt_text
    assert "<truncated>false</truncated>" in prompt_text
    assert "<omitted_files>" in prompt_text
    assert "<file>.env</file>" in prompt_text
    assert 'timestamp_utc="2026-10-21T02:00:00Z"' in prompt_text
    assert "</review_context>" in prompt_text
