"""Unit tests for bounded packet builder and privacy redaction."""

import os

from steadydev.models import ChangedFile, CheckReceipt
from steadydev.packet import (
    build_review_packet,
    distill_unified_diff,
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


def test_path_traversal_rejection() -> None:
    import pytest

    with pytest.raises(ValueError, match="Directory traversal"):
        normalize_path("src/../../etc/passwd")

    with pytest.raises(ValueError, match="Directory traversal"):
        normalize_path("../secret.py")


def test_nested_excluded_directories() -> None:
    assert is_allowlisted("subfolder/.git/config") is False
    assert is_allowlisted("packages/pkg/.venv/lib/site.py") is False
    assert is_allowlisted("frontend/node_modules/package.json") is False


def test_case_insensitive_env_and_sensitive_files() -> None:
    assert is_allowlisted(".ENV") is False
    assert is_allowlisted(".Env.local") is False
    assert is_allowlisted(".env.production") is False
    assert is_allowlisted(".env.example") is True
    # Sensitive credentials and keys
    assert is_allowlisted("id_rsa") is False
    assert is_allowlisted("id_ed25519") is False
    assert is_allowlisted("credentials.json") is False
    assert is_allowlisted("server.pem") is False
    assert is_allowlisted("private.key") is False


def test_sentry_dsn_and_token_redaction() -> None:
    raw = "DSN is https://abcdef1234567890abcdef1234567890@o1234.ingest.sentry.io/5678"
    red = redact_sensitive_text(raw)
    assert "abcdef1234567890" not in red
    assert "[REDACTED_SECRET]" in red


def test_c2_raw_username_redaction() -> None:
    username = os.environ.get("USERNAME") or os.environ.get("USER") or "TestUser"
    raw = f"Code authored by {username} in workspace"
    red = redact_sensitive_text(raw)
    assert username not in red
    assert "[DEVELOPER_USER]" in red


def test_diff_budgeting_defaults_and_caps() -> None:
    """Verifies that max_files is 6 and max_aggregate_diff_bytes is 12288 by default."""
    files = [
        ChangedFile(path=f"file{i}.py", diff="+" + "a" * 2500 + "\n")
        for i in range(1, 8)
    ]
    packet = build_review_packet(
        session_intention="Test diff budget",
        acceptance_criteria=["Pass"],
        changed_files=files,
        check_receipts=[],
    )
    # File 7 should be omitted because max_files is 6
    assert len(packet.changed_files) <= 6
    assert "file7.py" in packet.omitted_files
    # Total diff bytes should not exceed 12288
    total_bytes = sum(len(f.diff.encode("utf-8")) for f in packet.changed_files)
    assert total_bytes <= 12288 + 200  # allowing for the truncation notice tag
    assert packet.truncated is True


def test_distill_unified_diff_strips_boilerplate() -> None:
    raw_diff = (
        "diff --git a/src/app.py b/src/app.py\n"
        "index 1234567..abcdef8 100644\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,15 +1,18 @@\n"
        "+import os\n"
        "+import sys\n"
        "+import json\n"
        "+import re\n"
        " \n"
        "-        old_indent = 1\n"
        "+        def calculate(x: int) -> int:\n"
        "+            return x * 2\n"
        "+\n"
        "+        }\n"
        "+        );\n"
    )
    distilled, was_trunc = distill_unified_diff(raw_diff, max_lines=60, max_bytes=2500)
    assert was_trunc is False
    # Headers preserved
    assert "diff --git" in distilled
    assert "@@ -1,15 +1,18 @@" in distilled
    # Git metadata stripped
    assert "index 1234567" not in distilled
    # Imports preserved intact
    assert "import os" in distilled
    assert "import sys" in distilled
    assert "import json" in distilled
    # Semantic change and original indentation preserved
    assert "def calculate(x: int) -> int:" in distilled
    assert "        def calculate" in distilled
    # Delimiters preserved
    assert "+        }" in distilled
    assert "+        );" in distilled


def test_distill_c6_multi_file_preservation() -> None:
    """Verifies C-6: all 6 files are preserved under aggregate budget without dropping files."""
    files = [
        ChangedFile(path=f"src/file{i}.py", diff="+" + f"data_{i} = 1\n" * 100)
        for i in range(1, 7)
    ]
    packet = build_review_packet(
        session_intention="Test C-6 preservation",
        acceptance_criteria=["Preserve files"],
        changed_files=files,
        check_receipts=[],
        max_files=6,
        max_aggregate_diff_bytes=6000,
    )
    # No files dropped to omitted_files
    assert len(packet.changed_files) == 6
    assert len(packet.omitted_files) == 0
    # Every file has its path preserved
    paths = [cf.path for cf in packet.changed_files]
    for i in range(1, 7):
        assert f"src/file{i}.py" in paths
    assert packet.truncated is True


def test_distill_preserves_faithful_indentation_and_delimiters() -> None:
    """R13: Unified diff hunks must retain original indentation, imports, and delimiters."""
    raw_diff = """diff --git a/src/calc.py b/src/calc.py
--- a/src/calc.py
+++ b/src/calc.py
@@ -10,6 +10,12 @@
 import os
+import sys
+from pathlib import Path
+
+def calculate(val):
+    if val > 0:
+        return {
+            "result": val * 2,
+        }
+    return None
"""
    distilled, _truncated = distill_unified_diff(raw_diff)
    # Exact indentation must be preserved
    assert "        return {" in distilled, "Indentation inside block must be preserved"
    assert '            "result": val * 2,' in distilled, (
        "Nested indentation must be preserved"
    )
    # Closing delimiters must not be stripped
    assert "        }" in distilled, "Closing bracket must be preserved"
    # Import lines must not be stripped
    assert "+import sys" in distilled
    assert "+from pathlib import Path" in distilled
