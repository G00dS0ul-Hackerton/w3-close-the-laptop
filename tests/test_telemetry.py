"""Tests for Sentry AI Agent Tracing, strict allowlist sanitization, and secret-canary scrubbing."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from steadydev.models import (
    ChangedFile,
    CheckReceipt,
    Finding,
    FindingCategory,
    FindingStatus,
    ReviewPacket,
)
from steadydev.reviewer import Reviewer
from steadydev.telemetry import (
    ALLOWED_SPAN_DATA_KEYS,
    ALLOWED_SPAN_OPS,
    ALLOWED_SPAN_TAG_KEYS,
    InMemoryRecordingTransport,
    NoOpSpan,
    init_telemetry,
    is_telemetry_enabled,
    start_chat_span,
    start_review_span,
    start_tool_span,
)


def test_telemetry_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify telemetry is completely disabled and returns NoOpSpan by default."""
    monkeypatch.delenv("STEADYDEV_SENTRY_ENABLED", raising=False)
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    assert is_telemetry_enabled() is False
    assert init_telemetry() is False

    with start_review_span("p-1", "repo", 1, 1, 0, 1, "m1", "m2") as span:
        assert isinstance(span, NoOpSpan)
        span.set_data("test.key", "val")
        span.set_status("ok")

    with start_chat_span("gemma3:4b") as c_span:
        assert isinstance(c_span, NoOpSpan)

    with start_tool_span() as t_span:
        assert isinstance(t_span, NoOpSpan)


def test_in_memory_recording_transport_captures_envelopes() -> None:
    """Verify InMemoryRecordingTransport captures manual GenAI spans locally in memory."""
    transport = InMemoryRecordingTransport()
    initialized = init_telemetry(
        dsn="https://dummy_key@o0.ingest.sentry.io/12345",
        transport=transport,
        force_enable=True,
    )
    assert initialized is True

    with start_review_span(
        packet_id="pkt-test-01",
        repo_name="sample-repo",
        files_count=3,
        receipts_count=2,
        prior_findings_count=1,
        chunks_count=1,
        primary_model="gemma3:4b",
        fallback_model="qwen2.5-coder:3b",
        session_id="sess-abc-123",
    ) as review_span:
        with start_chat_span(
            model_name="gemma3:4b",
            chunk_index=1,
            total_chunks=1,
            files_count=3,
            diff_chars=1200,
        ) as chat_span:
            chat_span.set_data("gen_ai.usage.input_tokens", 450)
            chat_span.set_data("gen_ai.usage.output_tokens", 85)
            chat_span.set_data("gen_ai.usage.total_tokens", 535)
            chat_span.set_data("ollama.timing.total_duration_ms", 12500.0)
            chat_span.set_data("ollama.timing.load_duration_ms", 150.0)
            chat_span.set_data("ollama.timing.prompt_eval_duration_ms", 8500.0)
            chat_span.set_data("ollama.timing.eval_duration_ms", 3850.0)
            chat_span.set_status("ok")

        with start_tool_span(
            tool_name="ChecklistBaseline", reason="primary_mode"
        ) as tool_span:
            tool_span.set_data("baseline.findings_count", 0)
            tool_span.set_data("baseline.retired_count", 0)
            tool_span.set_status("ok")

        review_span.set_data("review.status", "clean")
        review_span.set_data("review.findings_count", 0)
        review_span.set_data("review.retired_count", 0)
        review_span.set_data("review.effective_model", "gemma3:4b")
        review_span.set_status("ok")

    # Flush spans into envelopes
    assert len(transport.envelopes) >= 1
    wire_text = transport.get_wire_text()
    assert "steadydev.review" in wire_text
    assert "gen_ai.invoke_agent" in wire_text
    assert "gen_ai.chat" in wire_text
    assert "535" in wire_text  # total tokens


def test_secret_canary_scrubbed_from_outbound_envelopes(tmp_path: Path) -> None:
    """Assert zero canary secrets (keys, passwords, paths, usernames, code) appear in wire payloads."""
    canary_tokens = [
        "sk-canary-secret-token-abcdef1234567890",
        "CanarySuperSecretPassword!2026",
        "G00dS0ul",
        "G00dS0ul🤡",
        "C:\\Users\\G00dS0ul🤡\\secret_repo",
        "CANARY_PROMPT_INSTRUCTION_DO_NOT_LEAK",
        "def canary_private_key(): return '0xdeadbeef'",
        "CANARY_ENV_DATABASE_PASSWORD_XYZ",
    ]

    transport = InMemoryRecordingTransport()
    init_telemetry(
        dsn="https://mock@sentry.test/999",
        transport=transport,
        force_enable=True,
    )

    # Build review packet containing canaries
    canary_file = ChangedFile(
        path="src/secret_service.py",
        status="modified",
        diff="""diff --git a/src/secret_service.py b/src/secret_service.py
--- a/src/secret_service.py
+++ b/src/secret_service.py
@@ -1,3 +1,6 @@
+def canary_private_key(): return '0xdeadbeef'
+# API_KEY = "sk-canary-secret-token-abcdef1234567890"
+# Password: CanarySuperSecretPassword!2026
""",
    )
    canary_receipt = CheckReceipt(
        receipt_id="rcpt-canary-01",
        command="pytest C:\\Users\\G00dS0ul🤡\\secret_repo\\test.py",
        exit_code=0,
        output_summary="CANARY_ENV_DATABASE_PASSWORD_XYZ verified",
        timestamp_utc="2026-10-23T15:00:00Z",
    )
    canary_finding = Finding(
        finding_id="fnd-canary-01",
        category=FindingCategory.EVIDENCE_MISMATCH,
        locator="src/secret_service.py:2",
        description="Found CANARY_PROMPT_INSTRUCTION_DO_NOT_LEAK in diff",
        evidence="def canary_private_key(): return '0xdeadbeef'",
        status=FindingStatus.OPEN,
    )

    packet = ReviewPacket(
        packet_id="pkt-canary-test",
        timestamp_utc="2026-10-23T15:00:00Z",
        repo_name="secret_repo",
        session_intention="Test canary scrubbing for user G00dS0ul🤡",
        acceptance_criteria=["Check CANARY_PROMPT_INSTRUCTION_DO_NOT_LEAK"],
        changed_files=[canary_file],
        check_receipts=[canary_receipt],
        prior_findings=[canary_finding],
    )

    # Mock Ollama client returning clean valid response
    mock_ollama = MagicMock()
    mock_ollama.chat.return_value = {
        "content": json.dumps(
            {
                "status": "clean",
                "findings": [],
                "retired_finding_ids": [],
                "closing_summary": "Clean summary",
                "restart_note": "Clean restart note",
            }
        ),
        "total_duration_ms": 1500.0,
        "load_duration_ms": 50.0,
        "prompt_eval_duration_ms": 1000.0,
        "eval_duration_ms": 450.0,
        "prompt_eval_count": 120,
        "eval_count": 45,
    }

    reviewer = Reviewer(ollama_client=mock_ollama)

    with start_review_span(
        packet_id=packet.packet_id,
        repo_name=packet.repo_name,
        files_count=len(packet.changed_files),
        receipts_count=len(packet.check_receipts),
        prior_findings_count=len(packet.prior_findings),
        chunks_count=1,
        primary_model="gemma3:4b",
        fallback_model="qwen2.5-coder:3b",
        session_id="sess-canary-test",
    ):
        reviewer.review(packet, model_name="gemma3:4b")

    wire_text = transport.get_wire_text()

    # CRITICAL SECURITY ASSERTION: Assert zero canary secrets leaked into telemetry wire text
    for token in canary_tokens:
        assert token not in wire_text, (
            f"Canary token '{token}' LEAKED into Sentry outbound envelope!"
        )
        assert token.lower() not in wire_text.lower(), (
            f"Canary token '{token}' leaked in lower-case scan!"
        )


def test_strict_span_attribute_allowlist() -> None:
    """Verify only allowed span ops and keys survive before_send_transaction scrubber."""
    transport = InMemoryRecordingTransport()
    init_telemetry(
        dsn="https://mock@sentry.test/999",
        transport=transport,
        force_enable=True,
    )

    with start_review_span(
        packet_id="pkt-allowlist-test",
        repo_name="clean-repo",
        files_count=1,
        receipts_count=1,
        prior_findings_count=0,
        chunks_count=1,
        primary_model="gemma3:4b",
        fallback_model="qwen2.5-coder:3b",
    ) as span:
        # Inject unapproved data key
        span.set_data("forbidden.diff_content", "+line that should never exist")
        span.set_data("forbidden.prompt_text", "Instructions to model")
        # Inject approved data key
        span.set_data("review.status", "clean")

    wire_text = transport.get_wire_text()
    assert "+line that should never exist" not in wire_text
    assert "Instructions to model" not in wire_text
    assert "clean" in wire_text

    # Inspect envelope event structure
    for env in transport.envelopes:
        for item in getattr(env, "items", []):
            event = None
            if hasattr(item, "get_bytes"):
                try:
                    event = json.loads(item.get_bytes().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    event = None
            if isinstance(event, dict) and event.get("type") == "transaction":
                # Check forbidden root keys are purged
                assert "breadcrumbs" not in event or not event["breadcrumbs"]
                assert "request" not in event
                assert "user" not in event
                assert "modules" not in event
                assert "server_name" not in event

                for child in event.get("spans", []):
                    assert child["op"] in ALLOWED_SPAN_OPS
                    for k in child.get("data", {}):
                        assert k in ALLOWED_SPAN_DATA_KEYS, (
                            f"Unapproved span data key: {k}"
                        )
                    for t in child.get("tags", {}):
                        assert t in ALLOWED_SPAN_TAG_KEYS, (
                            f"Unapproved span tag key: {t}"
                        )


def test_disabled_telemetry_clears_stale_trace_id() -> None:
    """R16: Disabling telemetry via set_telemetry_opt_in(False) must not leave a stale active trace_id on the DISABLED receipt."""
    from steadydev.telemetry import (
        ExportState,
        get_export_state,
        get_last_delivery_receipt,
        set_telemetry_opt_in,
    )

    transport = InMemoryRecordingTransport()
    init_telemetry(
        dsn="https://mock@sentry.test/999",
        transport=transport,
        force_enable=True,
    )

    with start_review_span(
        packet_id="pkt-trace-clear",
        repo_name="repo",
        files_count=1,
        receipts_count=0,
        prior_findings_count=0,
        chunks_count=1,
        primary_model="qwen2.5-coder:3b",
        fallback_model="gemma3:4b",
    ):
        pass

    # Now opt out
    set_telemetry_opt_in(False)
    assert get_export_state() == ExportState.DISABLED
    receipt = get_last_delivery_receipt()
    assert receipt.trace_id is None, (
        f"Expected trace_id to be None when telemetry is DISABLED, got {receipt.trace_id}"
    )

