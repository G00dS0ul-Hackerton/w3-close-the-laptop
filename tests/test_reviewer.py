"""Unit tests for Reviewer orchestrator."""

import json
from unittest.mock import MagicMock

from steadydev.models import ChangedFile, Finding, FindingCategory, ReviewPacket
from steadydev.ollama_client import OllamaClient, OllamaConnectionError
from steadydev.reviewer import Reviewer, strip_markdown_fences, validate_locator


def test_strip_markdown_fences() -> None:
    fenced = '```json\n{"status": "clean"}\n```'
    assert strip_markdown_fences(fenced) == '{"status": "clean"}'
    plain = '{"status": "clean"}'
    assert strip_markdown_fences(plain) == '{"status": "clean"}'


def test_ollama_client_default_timeout_is_unlimited() -> None:
    client = OllamaClient()
    assert client.timeout.read is None


def test_validate_locator() -> None:
    allowlisted = {"src/auth.py", "lib/ui.dart"}

    # Valid
    ok, err = validate_locator("src/auth.py:42", allowlisted)
    assert ok is True
    assert err is None

    # Path traversal rejected
    ok, err = validate_locator("../etc/passwd:1", allowlisted)
    assert ok is False
    assert "Path traversal" in err

    # Absolute drive rejected
    ok, err = validate_locator("C:/Users/file.py", allowlisted)
    assert ok is False

    # Out of scope file rejected
    ok, err = validate_locator("src/unknown.py:10", allowlisted)
    assert ok is False
    assert "was not in the modified diff" in err


def test_reviewer_baseline_execution(sample_clean_packet: ReviewPacket) -> None:
    reviewer = Reviewer()
    result = reviewer.review(sample_clean_packet, model_name=None)
    assert result.status == "clean"
    assert result.model_name == "baseline-checklist"

    result_explicit = reviewer.review(
        sample_clean_packet, model_name="baseline-checklist"
    )
    assert result_explicit.status == "clean"
    assert result_explicit.model_name == "baseline-checklist"

    result_slug = reviewer.review(sample_clean_packet, model_name="baseline")
    assert result_slug.status == "clean"
    assert result_slug.model_name == "baseline-checklist"


def test_reviewer_model_success(sample_clean_packet: ReviewPacket) -> None:
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.chat.return_value = {
        "content": '{"status": "clean", "findings": [], "closing_summary": "All checks pass", "restart_note": "Ready"}',
        "total_duration_ms": 1200.0,
        "load_duration_ms": 100.0,
    }
    reviewer = Reviewer(ollama_client=mock_client)
    result = reviewer.review(sample_clean_packet, model_name="qwen2.5-coder:3b")
    assert result.status == "clean"
    assert result.model_name == "qwen2.5-coder:3b"
    assert result.closing_summary == "All checks pass"
    assert result.raw_content.startswith('{"status"')
    assert isinstance(result.raw_json, dict)


def test_reviewer_forged_locator_downgraded(sample_clean_packet: ReviewPacket) -> None:
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.chat.return_value = {
        "content": '{"status": "findings_detected", "findings": [{"category": "evidence_mismatch", "locator": "src/ghost_file.py:99", "description": "Hallucinated issue"}], "closing_summary": "s", "restart_note": "r"}',
        "total_duration_ms": 1000.0,
    }
    reviewer = Reviewer(ollama_client=mock_client)
    result = reviewer.review(sample_clean_packet, model_name="gemma3:4b")
    assert result.status == "findings_detected"
    assert len(result.findings) == 1
    # Downgraded to needs_judgment because locator wasn't in diff
    assert result.findings[0].category == FindingCategory.NEEDS_JUDGMENT
    assert "unverified locator" in result.findings[0].description


def test_reviewer_fallback_on_outage(sample_clean_packet: ReviewPacket) -> None:
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.chat.side_effect = OllamaConnectionError("Daemon offline")

    reviewer = Reviewer(ollama_client=mock_client)
    # With fallback enabled (default): must be explicit status fallback_baseline!
    result = reviewer.review(
        sample_clean_packet, model_name="gemma3:4b", use_baseline_fallback=True
    )
    assert result.status == "fallback_baseline"
    assert result.model_name == "gemma3:4b-fallback-baseline"
    assert "Fell back to baseline" in result.error

    # Without fallback
    result_no_fallback = reviewer.review(
        sample_clean_packet, model_name="gemma3:4b", use_baseline_fallback=False
    )
    assert result_no_fallback.status == "unavailable"
    assert "Daemon offline" in result_no_fallback.error


def test_reviewer_missing_keys_triggers_fallback(
    sample_clean_packet: ReviewPacket,
) -> None:
    mock_client = MagicMock(spec=OllamaClient)
    # Model emitted incomplete dictionary missing restart_note and closing_summary
    mock_client.chat.return_value = {
        "content": '{"status": "clean", "findings": []}',
        "total_duration_ms": 500.0,
    }
    reviewer = Reviewer(ollama_client=mock_client)
    result = reviewer.review(
        sample_clean_packet, model_name="gemma3:4b", use_baseline_fallback=True
    )
    assert result.status == "fallback_baseline"
    assert "Incomplete model response" in result.error


def test_reviewer_deferred_lifecycle_state_preserved(
    sample_clean_packet: ReviewPacket,
) -> None:
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.chat.return_value = {
        "content": '{"status": "findings_detected", "findings": [{"category": "deferred", "locator": "src/auth.py:10", "description": "Deferred migration", "evidence": "text"}], "closing_summary": "summary", "restart_note": "note"}',
        "total_duration_ms": 800.0,
    }
    reviewer = Reviewer(ollama_client=mock_client)
    result = reviewer.review(sample_clean_packet, model_name="gemma3:4b")
    assert result.status == "findings_detected"
    assert len(result.findings) == 1
    # Status preserved as DEFERRED lifecycle state
    from steadydev.models import FindingStatus

    assert result.findings[0].status == FindingStatus.DEFERRED


def test_reviewer_unsupported_retirement_id_flagged(
    sample_clean_packet: ReviewPacket,
) -> None:
    mock_client = MagicMock(spec=OllamaClient)
    # Model proposes retiring f-nonexistent-99 which is not in prior_findings
    mock_client.chat.return_value = {
        "content": '{"status": "clean", "findings": [], "retired_finding_ids": ["f-nonexistent-99"], "closing_summary": "summary", "restart_note": "note"}',
        "total_duration_ms": 800.0,
    }
    reviewer = Reviewer(ollama_client=mock_client)
    result = reviewer.review(sample_clean_packet, model_name="gemma3:4b")
    assert result.status == "findings_detected"
    assert any(
        "Unsupported retirement ID 'f-nonexistent-99'" in f.description
        for f in result.findings
    )


def test_reviewer_rejects_unrelated_receipt_retirement() -> None:
    prior = Finding(
        finding_id="f-prior-nav-01",
        category=FindingCategory.UNVERIFIED,
        locator="lib/widgets/nav_bar.dart:18",
        description="No check recorded for modified layout.",
    )
    packet = ReviewPacket(
        packet_id="pkt-t06b-test",
        timestamp_utc="2026-10-21T02:00:00Z",
        repo_name="repo",
        session_intention="Refactor string utility",
        acceptance_criteria=["Unit test passes"],
        changed_files=[
            {
                "path": "lib/utils/string_helper.dart",
                "status": "modified",
                "diff": "+trim\n",
            }
        ],
        check_receipts=[
            {
                "receipt_id": "rcpt-t06b-01",
                "command": "flutter test test/string_helper_test.dart",
                "exit_code": 0,
                "output_summary": "1 passed (string helper only, no layout checks)",
                "timestamp_utc": "2026-10-21T02:00:00Z",
            }
        ],
        prior_findings=[prior],
    )
    mock_client = MagicMock(spec=OllamaClient)
    # Model mistakenly proposed retiring f-prior-nav-01 with unrelated receipt
    mock_client.chat.return_value = {
        "content": '{"status": "clean", "findings": [], "retired_finding_ids": ["f-prior-nav-01"], "closing_summary": "Helper updated", "restart_note": "Ready"}',
        "total_duration_ms": 1000.0,
    }
    reviewer = Reviewer(ollama_client=mock_client)
    res = reviewer.review(
        packet, model_name="qwen2.5-coder:3b", use_baseline_fallback=False
    )
    # Unrelated receipt must NOT retire layout finding!
    assert "f-prior-nav-01" not in res.retired_finding_ids
    assert res.status == "findings_detected"
    assert any("f-prior-nav-01" in f.description for f in res.findings)


def test_reviewer_accepts_relevant_receipt_retirement() -> None:
    prior = Finding(
        finding_id="f-prior-nav-01",
        category=FindingCategory.UNVERIFIED,
        locator="lib/widgets/nav_bar.dart:18",
        description="No check recorded for modified layout.",
    )
    packet = ReviewPacket(
        packet_id="pkt-t06a-test",
        timestamp_utc="2026-10-21T02:00:00Z",
        repo_name="repo",
        session_intention="Add viewport test",
        acceptance_criteria=["Viewport verified"],
        changed_files=[
            {
                "path": "test/nav_bar_viewport_test.dart",
                "status": "added",
                "diff": "+test\n",
            }
        ],
        check_receipts=[
            {
                "receipt_id": "rcpt-t06a-01",
                "command": "flutter test test/nav_bar_viewport_test.dart",
                "exit_code": 0,
                "output_summary": "1 passed, viewport verified across breakpoints",
                "timestamp_utc": "2026-10-21T02:00:00Z",
            }
        ],
        prior_findings=[prior],
    )
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.chat.return_value = {
        "content": '{"status": "clean", "findings": [], "retired_finding_ids": ["f-prior-nav-01"], "closing_summary": "Viewport test verified", "restart_note": "Ready"}',
        "total_duration_ms": 1000.0,
    }
    reviewer = Reviewer(ollama_client=mock_client)
    res = reviewer.review(
        packet, model_name="qwen2.5-coder:3b", use_baseline_fallback=False
    )
    assert "f-prior-nav-01" in res.retired_finding_ids
    assert res.status == "clean"


def test_reviewer_prunes_reemitted_retired_finding() -> None:
    prior = Finding(
        finding_id="f-prior-nav-01",
        category=FindingCategory.UNVERIFIED,
        locator="lib/widgets/nav_bar.dart:18",
        description="No check recorded for modified layout.",
    )
    packet = ReviewPacket(
        packet_id="pkt-t06a-test",
        timestamp_utc="2026-10-21T02:00:00Z",
        repo_name="repo",
        session_intention="Add viewport test",
        acceptance_criteria=["Viewport verified"],
        changed_files=[
            {
                "path": "test/nav_bar_viewport_test.dart",
                "status": "added",
                "diff": "+test\n",
            }
        ],
        check_receipts=[
            {
                "receipt_id": "rcpt-t06a-01",
                "command": "flutter test test/nav_bar_viewport_test.dart",
                "exit_code": 0,
                "output_summary": "1 passed, viewport verified",
                "timestamp_utc": "2026-10-21T02:00:00Z",
            }
        ],
        prior_findings=[prior],
    )
    mock_client = MagicMock(spec=OllamaClient)
    # Model retired ID but also duplicated it into findings
    mock_client.chat.return_value = {
        "content": '{"status": "clean", "findings": [{"category": "unverified", "locator": "lib/widgets/nav_bar.dart:18", "description": "No check recorded for modified layout.", "evidence": ""}], "retired_finding_ids": ["f-prior-nav-01"], "closing_summary": "Viewport verified", "restart_note": "Ready"}',
        "total_duration_ms": 1000.0,
    }
    reviewer = Reviewer(ollama_client=mock_client)
    res = reviewer.review(
        packet, model_name="qwen2.5-coder:3b", use_baseline_fallback=False
    )
    assert "f-prior-nav-01" in res.retired_finding_ids
    # Duplicate re-emitted finding MUST be pruned!
    assert len(res.findings) == 0
    assert res.status == "clean"


def test_reviewer_parse_error_retains_timing_metrics(
    sample_clean_packet: ReviewPacket,
) -> None:
    mock_client = MagicMock(spec=OllamaClient)
    # Simulates Gemma emitting {} with Ollama timing metrics
    mock_client.chat.return_value = {
        "content": "{}",
        "total_duration_ms": 15200.0,
        "load_duration_ms": 500.0,
        "eval_duration_ms": 25.0,
    }
    reviewer = Reviewer(ollama_client=mock_client)
    res = reviewer.review(
        sample_clean_packet, model_name="gemma3:4b", use_baseline_fallback=False
    )
    assert res.status == "parse_error"
    assert res.timing_ms.get("total_duration_ms") == 15200.0
    assert res.timing_ms.get("load_duration_ms") == 500.0
    assert res.timing_ms.get("eval_duration_ms") == 25.0


def test_reviewer_prior_finding_locator_not_flagged_as_traversal() -> None:
    """Prior finding locators referencing files not touched in the current diff must not be flagged as invalid."""
    prior = Finding(
        finding_id="f-prior-nav-01",
        category=FindingCategory.UNVERIFIED,
        locator="lib/widgets/nav_bar.dart:18",
        description="No check recorded for modified layout.",
    )
    packet = ReviewPacket(
        packet_id="pkt-t06b-test",
        timestamp_utc="2026-10-21T02:00:00Z",
        repo_name="repo",
        session_intention="Fix string utility",
        acceptance_criteria=["Unit test passes"],
        changed_files=[
            {
                "path": "lib/utils/string_helper.dart",
                "status": "modified",
                "diff": "+trim\n",
            }
        ],
        check_receipts=[
            {
                "receipt_id": "rcpt-01",
                "command": "flutter test test/string_helper_test.dart",
                "exit_code": 0,
                "output_summary": "1 passed",
                "timestamp_utc": "2026-10-21T02:00:00Z",
            }
        ],
        prior_findings=[prior],
    )
    mock_client = MagicMock(spec=OllamaClient)
    # Model comments on the prior finding locator
    mock_client.chat.return_value = {
        "content": '{"status": "findings_detected", "findings": [{"category": "unverified", "locator": "lib/widgets/nav_bar.dart:18", "description": "Prior navbar check still open.", "evidence": ""}], "retired_finding_ids": [], "closing_summary": "Helper tested; navbar still open.", "restart_note": "Add navbar viewport test."}',
        "total_duration_ms": 1000.0,
    }
    reviewer = Reviewer(ollama_client=mock_client)
    res = reviewer.review(
        packet, model_name="qwen2.5-coder:3b", use_baseline_fallback=False
    )
    assert res.status == "findings_detected"
    assert len(res.findings) == 1
    # Locator must be validated and not downgraded to needs_judgment with an unverified locator warning!
    assert res.findings[0].category == FindingCategory.UNVERIFIED
    assert "unverified locator" not in res.findings[0].description


def test_reviewer_cascade_gemma_primary_success(
    sample_clean_packet: ReviewPacket,
) -> None:
    """Cascade primary: gemma3:4b succeeds without needing fallback."""
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.chat.return_value = {
        "content": '{"status": "clean", "findings": [], "closing_summary": "Gemma review clean", "restart_note": "Gemma ready"}',
        "total_duration_ms": 25000.0,
    }
    reviewer = Reviewer(ollama_client=mock_client)
    res = reviewer.review(sample_clean_packet, model_name="gemma3:4b")
    assert res.status == "clean"
    assert res.model_name == "gemma3:4b"
    assert res.closing_summary == "Gemma review clean"
    assert mock_client.chat.call_count == 1
    assert mock_client.chat.call_args[1]["model"] == "gemma3:4b"


def test_reviewer_cascade_gemma_timeout_qwen_fallback_success(
    sample_clean_packet: ReviewPacket,
) -> None:
    """Cascade fallback: gemma3:4b times out, qwen2.5-coder:3b is called and succeeds."""
    from steadydev.ollama_client import OllamaTimeoutError

    mock_client = MagicMock(spec=OllamaClient)

    def side_effect(model: str, **kwargs):
        if model == "gemma3:4b":
            raise OllamaTimeoutError("Gemma timed out on CPU after 180s")
        return {
            "content": '{"status": "clean", "findings": [], "closing_summary": "Qwen fallback review clean", "restart_note": "Qwen ready"}',
            "total_duration_ms": 15000.0,
        }

    mock_client.chat.side_effect = side_effect
    reviewer = Reviewer(ollama_client=mock_client)
    res = reviewer.review(
        sample_clean_packet,
        model_name="gemma3:4b",
        fallback_model_name="qwen2.5-coder:3b",
    )
    assert res.status == "clean"
    assert res.model_name == "qwen2.5-coder:3b"
    assert res.closing_summary == "Qwen fallback review clean"
    assert mock_client.chat.call_count == 2
    assert "Fell back to fallback model" in (res.error or "")


def test_reviewer_cascade_gemma_schema_error_qwen_fallback_success(
    sample_clean_packet: ReviewPacket,
) -> None:
    """Cascade fallback: gemma3:4b returns broken JSON, qwen succeeds."""
    mock_client = MagicMock(spec=OllamaClient)

    def side_effect(model: str, **kwargs):
        if model == "gemma3:4b":
            return {
                "content": '{"status": "success", "message": "Done"}',
                "total_duration_ms": 2000.0,
            }
        return {
            "content": '{"status": "clean", "findings": [], "closing_summary": "Qwen rescued review", "restart_note": "Qwen ready"}',
            "total_duration_ms": 3000.0,
        }

    mock_client.chat.side_effect = side_effect
    reviewer = Reviewer(ollama_client=mock_client)
    res = reviewer.review(
        sample_clean_packet,
        model_name="gemma3:4b",
        fallback_model_name="qwen2.5-coder:3b",
    )
    assert res.status == "clean"
    assert res.model_name == "qwen2.5-coder:3b"
    assert mock_client.chat.call_count == 2


def test_reviewer_cascade_both_models_fail_drops_to_baseline(
    sample_clean_packet: ReviewPacket,
) -> None:
    """Cascade safety floor: both Gemma and Qwen time out, engine drops to baseline."""
    from steadydev.ollama_client import OllamaTimeoutError

    mock_client = MagicMock(spec=OllamaClient)
    mock_client.chat.side_effect = OllamaTimeoutError("Timed out")

    reviewer = Reviewer(ollama_client=mock_client)
    res = reviewer.review(
        sample_clean_packet,
        model_name="gemma3:4b",
        fallback_model_name="qwen2.5-coder:3b",
        use_baseline_fallback=True,
    )
    assert res.status == "fallback_baseline"
    assert "baseline" in res.model_name
    assert mock_client.chat.call_count == 2
    assert "Fell back to baseline" in res.error


def test_reviewer_cascade_connection_error_short_circuits_to_baseline(
    sample_clean_packet: ReviewPacket,
) -> None:
    """Connection short-circuit: daemon offline drops immediately without wasting calls on Qwen."""
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.chat.side_effect = OllamaConnectionError("Connection refused")

    reviewer = Reviewer(ollama_client=mock_client)
    res = reviewer.review(
        sample_clean_packet,
        model_name="gemma3:4b",
        fallback_model_name="qwen2.5-coder:3b",
        use_baseline_fallback=True,
    )
    assert res.status == "fallback_baseline"
    assert "baseline" in res.model_name
    # Crucial: chat must only be called ONCE!
    assert mock_client.chat.call_count == 1


def test_reviewer_partition_into_chunks(sample_clean_packet: ReviewPacket) -> None:
    reviewer = Reviewer()
    # 1 file returns single chunk
    chunks1 = reviewer._partition_into_chunks(sample_clean_packet)
    assert len(chunks1) == 1

    # 4 files partitioned into 2 chunks (max 2 files per chunk)
    files = [
        ChangedFile(path=f"src/file{i}.py", diff=f"+x{i} = 1\n") for i in range(1, 5)
    ]
    packet4 = ReviewPacket(
        packet_id="pkt-4",
        timestamp_utc="2026-10-22T00:00:00Z",
        repo_name="repo",
        session_intention="Test 4 files",
        acceptance_criteria=["Pass"],
        changed_files=files,
    )
    chunks2 = reviewer._partition_into_chunks(packet4)
    assert len(chunks2) == 2
    assert len(chunks2[0].changed_files) == 2
    assert len(chunks2[1].changed_files) == 2
    assert chunks2[0].changed_files[0].path == "src/file1.py"
    assert chunks2[1].changed_files[0].path == "src/file3.py"


def test_reviewer_map_reduce_with_progress_callback() -> None:
    mock_client = MagicMock(spec=OllamaClient)

    # Chunk 1 response, Chunk 2 response, Synthesis response
    chunk1_json = '{"status": "findings_detected", "findings": [{"category": "unverified", "locator": "src/file1.py:10", "description": "No check"}], "closing_summary": "c1", "restart_note": "r1"}'
    chunk2_json = '{"status": "clean", "findings": [], "closing_summary": "c2", "restart_note": "r2"}'
    synthesis_json = '{"closing_summary": "Synthesized 4 files", "restart_note": "Run tests on file1 tomorrow"}'

    mock_client.chat.side_effect = [
        {"content": chunk1_json, "total_duration_ms": 500.0},
        {"content": chunk2_json, "total_duration_ms": 400.0},
        {"content": synthesis_json, "total_duration_ms": 300.0},
    ]

    files = [
        ChangedFile(path=f"src/file{i}.py", diff=f"+x{i} = 1\n") for i in range(1, 5)
    ]
    packet = ReviewPacket(
        packet_id="pkt-mr",
        timestamp_utc="2026-10-22T00:00:00Z",
        repo_name="repo",
        session_intention="Test map reduce",
        acceptance_criteria=["Verify 4 files"],
        changed_files=files,
    )

    progress_events: list[tuple[int, int, str]] = []

    def callback(cur: int, tot: int, desc: str) -> None:
        progress_events.append((cur, tot, desc))

    reviewer = Reviewer(ollama_client=mock_client)
    res = reviewer.review(packet, model_name="gemma3:4b", progress_callback=callback)

    assert res.status == "findings_detected"
    assert len(res.findings) == 1
    assert res.findings[0].locator == "src/file1.py:10"
    assert res.closing_summary == "Synthesized 4 files"
    assert res.restart_note == "Run tests on file1 tomorrow"

    # Verify progress events: Chunk 1 start & done, Chunk 2 start & done, Synthesis
    assert len(progress_events) == 5
    assert progress_events[0][0] == 1
    assert progress_events[0][1] == 2
    assert "file1.py" in progress_events[0][2]
    assert progress_events[2][0] == 2
    assert progress_events[2][1] == 2
    assert "file3.py" in progress_events[2][2]
    assert "Synthesizing" in progress_events[4][2]


def test_fallback_unloads_primary_model_before_secondary() -> None:
    """R11: When primary model fails, unload_model must be called before querying fallback."""
    mock_client = MagicMock(spec=OllamaClient)

    # Primary fails with malformed JSON; fallback succeeds
    call_order: list[str] = []

    def mock_chat(model: str, *args, **kwargs):
        call_order.append(f"chat:{model}")
        if model == "gemma3:4b":
            return {"content": "not-valid-json", "total_duration_ms": 100.0}
        return {
            "content": '{"status": "clean", "findings": [], "closing_summary": "Qwen clean", "restart_note": "Qwen note"}',
            "total_duration_ms": 100.0,
        }

    def mock_unload(model: str):
        call_order.append(f"unload:{model}")
        return True

    mock_client.chat.side_effect = mock_chat
    mock_client.unload_model.side_effect = mock_unload

    packet = ReviewPacket(
        packet_id="pkt-unload",
        timestamp_utc="2026-10-23T00:00:00Z",
        repo_name="repo",
        session_intention="Test unload",
        acceptance_criteria=["Pass"],
        changed_files=[ChangedFile(path="src/app.py", diff="+print(1)\n")],
    )

    reviewer = Reviewer(ollama_client=mock_client)
    res = reviewer.review(
        packet, model_name="gemma3:4b", fallback_model_name="qwen2.5-coder:3b"
    )

    assert res.status == "clean"
    # Assert that unload:gemma3:4b occurred before chat:qwen2.5-coder:3b
    assert "unload:gemma3:4b" in call_order
    unload_idx = call_order.index("unload:gemma3:4b")
    qwen_idx = call_order.index("chat:qwen2.5-coder:3b")
    assert unload_idx < qwen_idx, "Primary model must be unloaded before fallback runs"


def test_workflow_budget_timeout_preserves_completed_chunks_and_uses_baseline_floor() -> (
    None
):
    """R12: Total workflow budget expiry preserves completed chunk findings and falls back to baseline."""
    mock_client = MagicMock(spec=OllamaClient)

    chunk1_json = '{"status": "findings_detected", "findings": [{"category": "unverified", "locator": "src/file1.py:5", "description": "Chunk 1 finding"}], "closing_summary": "c1", "restart_note": "r1"}'

    # First call succeeds for chunk 1; second call would be chunk 2
    mock_client.chat.side_effect = [
        {"content": chunk1_json, "total_duration_ms": 100.0},
    ]

    files = [
        ChangedFile(path="src/file1.py", diff="+x1 = 1\n"),
        ChangedFile(path="src/file2.py", diff="+x2 = 2\n"),
        ChangedFile(path="src/file3.py", diff="+x3 = 3\n"),
        ChangedFile(path="src/file4.py", diff="+x4 = 4\n"),
    ]
    packet = ReviewPacket(
        packet_id="pkt-budget",
        timestamp_utc="2026-10-23T00:00:00Z",
        repo_name="repo",
        session_intention="Test budget",
        acceptance_criteria=["Verify 4 files"],
        changed_files=files,
    )

    reviewer = Reviewer(ollama_client=mock_client)
    from unittest.mock import patch

    current_time = [0.0]

    def advancing_monotonic():
        return current_time[0]

    def mock_chat_advance(*args, **kwargs):
        # Advance time past workflow deadline during chunk 1 execution
        current_time[0] = 500.0
        return {"content": chunk1_json, "total_duration_ms": 100.0}

    mock_client.chat.side_effect = mock_chat_advance

    with patch("time.monotonic", side_effect=advancing_monotonic):
        res = reviewer.review(
            packet,
            model_name="gemma3:4b",
            workflow_timeout_seconds=5.0,
        )

    # Chunk 1's findings MUST be preserved
    assert any(f.locator == "src/file1.py:5" for f in res.findings)
    # Total calls to chat should not have attempted synthesis with Ollama
    assert mock_client.chat.call_count <= 2
    # Result must indicate partial timeout
    assert "timeout" in (res.error or "").lower() or "timeout" in res.status.lower()


def test_ollama_client_default_num_ctx_headroom() -> None:
    """R13: OllamaClient.chat must send num_ctx >= 4096 and num_predict >= 1024 so ~2000-token prompts do not truncate with done_reason='length'."""
    client = OllamaClient()
    captured_payload: dict = {}

    class DummyResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "message": {"content": '{"status":"clean","findings":[]}'},
                "done_reason": "stop",
                "total_duration": 1000000,
                "prompt_eval_count": 1950,
                "eval_count": 120,
            }

    mock_http = MagicMock()

    def fake_post(url: str, json: dict, **kwargs: object) -> DummyResponse:
        captured_payload.update(json)
        return DummyResponse()

    mock_http.post.side_effect = fake_post
    client._client = mock_http

    client.chat(model="qwen2.5-coder:3b", messages=[{"role": "user", "content": "hi"}])
    options = captured_payload.get("options", {})
    assert options.get("num_ctx", 0) >= 4096, (
        f"Expected num_ctx >= 4096 to prevent 2048-token truncation, got {options.get('num_ctx')}"
    )
    assert options.get("num_predict", 0) >= 1024, (
        f"Expected num_predict >= 1024, got {options.get('num_predict')}"
    )


def test_multichunk_no_baseline_fallback_and_distinct_secondary() -> None:
    """R14: Multi-chunk review with use_baseline_fallback=False must not substitute ChecklistBaseline on failure, and primary=qwen2.5-coder:3b with fallback=gemma3:4b must try gemma3:4b."""
    from steadydev.ollama_client import OllamaTimeoutError

    mock_client = MagicMock(spec=OllamaClient)
    call_models: list[str] = []

    def mock_chat(model: str, *args, **kwargs):
        call_models.append(model)
        raise OllamaTimeoutError(f"{model} timed out")

    mock_client.chat.side_effect = mock_chat
    mock_client.unload_model.return_value = True

    files = [
        ChangedFile(path="src/file1.py", diff="# TODO: unverified item\n+x1 = 1\n"),
        ChangedFile(path="src/file2.py", diff="+x2 = 2\n"),
        ChangedFile(path="src/file3.py", diff="+x3 = 3\n"),
    ]
    packet = ReviewPacket(
        packet_id="pkt-no-baseline",
        timestamp_utc="2026-10-24T00:00:00Z",
        repo_name="repo",
        session_intention="Test no baseline fallback",
        acceptance_criteria=["Verify all files"],
        changed_files=files,
    )

    reviewer = Reviewer(ollama_client=mock_client)
    res = reviewer.review(
        packet,
        model_name="qwen2.5-coder:3b",
        fallback_model_name="gemma3:4b",
        use_baseline_fallback=False,
        workflow_timeout_seconds=None,
    )

    # Should have attempted primary (qwen2.5-coder:3b) and secondary (gemma3:4b)
    assert "qwen2.5-coder:3b" in call_models
    assert "gemma3:4b" in call_models
    # Must NOT have substituted ChecklistBaseline findings when use_baseline_fallback=False
    assert res.status == "unavailable"
    assert res.findings == []
    assert all(
        cp.resolved_engine != "baseline-checklist" for cp in res.chunk_provenance
    )


def test_invoke_single_model_resilient_to_missing_restart_note() -> None:
    """Intermediate chunks or models that omit restart_note or closing_summary must NOT be rejected as schema_invalid."""
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.chat.return_value = {
        "content": json.dumps(
            {
                "status": "findings_detected",
                "findings": [
                    {
                        "category": "evidence_mismatch",
                        "locator": "src/app.py:10",
                        "description": "App divergence",
                        "evidence": "print('bad')",
                    }
                ],
                "closing_summary": "Reviewed app.py",
                # Note: "restart_note" omitted by model
            }
        ),
        "model": "gemma3:4b",
        "done_reason": "stop",
        "total_duration_ms": 150.0,
        "prompt_eval_count": 1800,
        "eval_count": 105,
    }

    reviewer = Reviewer(ollama_client=mock_client)
    parsed, _timings, _raw, err_msg, attempt = reviewer._invoke_single_model(
        model_name="gemma3:4b",
        messages=[{"role": "user", "content": "review"}],
        chunk_index=1,
        total_chunks=6,
    )

    assert err_msg is None, f"Expected err_msg to be None, got: {err_msg}"
    assert parsed is not None
    assert attempt.outcome == "success"
    assert parsed.get("restart_note") == ""
    assert len(parsed.get("findings", [])) == 1
    assert parsed["findings"][0]["locator"] == "src/app.py:10"
