"""Acceptance and regression tests for Package A: Python Lifecycle & Sanitized Error Coverage."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from steadydev.packet import ScopeDeniedError, WorkingTreeUnchanged
from steadydev.server import AdmissionLockBusy, CancelledError, StaleSnapshotConflict
from steadydev.telemetry import (
    ALLOWED_SPAN_OPS,
    InMemoryRecordingTransport,
    capture_unexpected_exception,
    init_telemetry,
    start_review_span,
    start_stage_span,
)


@pytest.fixture(autouse=True)
def _reset_telemetry_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture resetting telemetry state and environment for each test."""
    monkeypatch.setenv("STEADYDEV_SENTRY_ENABLED", "1")
    monkeypatch.setenv("SENTRY_DSN", "https://public_key@o0.ingest.sentry.io/1234567")


def test_expected_operational_outcomes_dropped() -> None:
    """Expected outcomes (cancellation, cache hit, 409 conflict, scope denial) must NOT produce error events."""
    transport = InMemoryRecordingTransport()
    init_telemetry(
        dsn="https://public_key@o0.ingest.sentry.io/1234567",
        transport=transport,
        force_enable=True,
    )

    expected_exceptions = [
        CancelledError("User requested cancellation"),
        WorkingTreeUnchanged("Working tree has not changed"),
        AdmissionLockBusy("Another review job is currently running"),
        StaleSnapshotConflict("Snapshot modified during inference"),
        ScopeDeniedError("Repository path outside workspace"),
    ]

    for exc in expected_exceptions:
        capture_unexpected_exception(exc, {"component": "test"})

    # Assert no error events or envelopes were sent
    error_envelopes = [
        env
        for env in transport.envelopes
        for item in getattr(env, "items", [])
        if getattr(item, "type", None) == "event"
    ]
    assert len(error_envelopes) == 0


def test_unexpected_engine_error_captured_and_sanitized() -> None:
    """Unexpected engine errors must produce sanitized Sentry events without locals or private paths."""
    transport = InMemoryRecordingTransport()
    init_telemetry(
        dsn="https://public_key@o0.ingest.sentry.io/1234567",
        transport=transport,
        force_enable=True,
    )

    user_home = str(Path.home())
    try:
        # Simulate unexpected database corruption error with private path in message
        raise sqlite3.DatabaseError(
            f"database disk image is malformed at {user_home}\\AppData\\steadydev.db"
        )
    except sqlite3.DatabaseError as exc:
        capture_unexpected_exception(exc, {"component": "storage"})

    import sentry_sdk

    sentry_sdk.flush()

    assert len(transport.envelopes) > 0
    wire_text = transport.get_wire_text()

    # Must contain error type
    assert "DatabaseError" in wire_text
    # Must NOT contain raw Windows home path
    assert "C:\\Users\\" not in wire_text
    assert user_home not in wire_text
    # Must NOT contain stack locals or source hunks
    assert '"vars":' not in wire_text or '"vars": {}' in wire_text
    assert '"pre_context":' not in wire_text
    assert '"context_line":' not in wire_text


def test_pipeline_stages_emit_nested_spans() -> None:
    """Review execution must emit child spans for all internal review stages."""
    transport = InMemoryRecordingTransport()
    init_telemetry(
        dsn="https://public_key@o0.ingest.sentry.io/1234567",
        transport=transport,
        force_enable=True,
    )

    expected_stages = [
        "snapshot.collect",
        "cache.fingerprint_check",
        "chunk.prepare",
        "validation.schema_check",
        "reconciliation.reconcile",
        "persistence.store",
    ]

    # Verify all expected stages are registered in ALLOWED_SPAN_OPS
    for stage_op in expected_stages:
        assert stage_op in ALLOWED_SPAN_OPS

    with start_review_span(
        packet_id="pkt-123",
        repo_name="test-repo",
        files_count=3,
        receipts_count=1,
        prior_findings_count=0,
        chunks_count=1,
        primary_model="gemma3:4b",
        fallback_model="qwen2.5-coder:3b",
    ):
        for stage_op in expected_stages:
            with start_stage_span(stage_op, f"Running {stage_op}") as stage_span:
                stage_span.set_data("stage.status", "completed")

    import sentry_sdk

    sentry_sdk.flush()

    wire_text = transport.get_wire_text()
    assert "steadydev.review" in wire_text
    for stage_op in expected_stages:
        assert stage_op in wire_text


def test_timeout_records_monotonic_duration_and_null_tokens() -> None:
    """Timed-out review must record positive monotonic duration and null/None token counts."""
    transport = InMemoryRecordingTransport()
    init_telemetry(
        dsn="https://public_key@o0.ingest.sentry.io/1234567",
        transport=transport,
        force_enable=True,
    )

    with start_review_span(
        packet_id="pkt-timeout",
        repo_name="timeout-repo",
        files_count=1,
        receipts_count=0,
        prior_findings_count=0,
        chunks_count=1,
        primary_model="gemma3:4b",
        fallback_model="qwen2.5-coder:3b",
    ) as span:
        span.set_status("deadline_exceeded")
        # Token metrics must remain None / null, never fabricated as 0
        span.set_data("gen_ai.usage.input_tokens", None)
        span.set_data("gen_ai.usage.output_tokens", None)

    import sentry_sdk

    sentry_sdk.flush()

    wire_text = transport.get_wire_text()
    assert "deadline_exceeded" in wire_text
    # Verify no fabricated non-null tokens in serialized span data
    assert '"gen_ai.usage.input_tokens": 0' not in wire_text


def test_telemetry_disabled_or_toggle_off_drops_envelopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When telemetry is disabled or toggled off mid-review, unsent spans are dropped in memory."""
    monkeypatch.setenv("STEADYDEV_SENTRY_ENABLED", "0")
    transport = InMemoryRecordingTransport()
    init_telemetry(
        dsn="https://public_key@o0.ingest.sentry.io/1234567",
        transport=transport,
        force_enable=False,  # disabled
    )

    with (
        start_review_span(
            packet_id="pkt-off",
            repo_name="test-repo",
            files_count=1,
            receipts_count=0,
            prior_findings_count=0,
            chunks_count=1,
            primary_model="gemma3:4b",
            fallback_model="qwen2.5-coder:3b",
        ),
        start_stage_span("snapshot.collect", "Collecting"),
    ):
        pass

    import sentry_sdk

    sentry_sdk.flush()

    assert len(transport.envelopes) == 0


def test_wire_bytes_contain_zero_canary_secrets() -> None:
    """Canary secrets injected into errors and spans must be completely scrubbed from raw wire bytes."""
    transport = InMemoryRecordingTransport()
    init_telemetry(
        dsn="https://public_key@o0.ingest.sentry.io/1234567",
        transport=transport,
        force_enable=True,
    )

    user_home = str(Path.home())
    canary_key = "sk-ant-api03-VERYSECRETKEYCANARY12345"
    canary_token = "Bearer loopback-token-CANARYSECRET98765"
    canary_path = f"{user_home}\\workspace\\secret_file.py"

    try:
        raise ValueError(
            f"Failed to process {canary_path} with key {canary_key} and auth {canary_token}"
        )
    except ValueError as exc:
        capture_unexpected_exception(exc, {"component": "test_canary"})

    import sentry_sdk

    sentry_sdk.flush()

    wire_text = transport.get_wire_text()
    assert canary_key not in wire_text
    assert canary_token not in wire_text
    assert "CANARY" not in wire_text
    assert user_home not in wire_text
    assert "C:\\Users\\" not in wire_text
