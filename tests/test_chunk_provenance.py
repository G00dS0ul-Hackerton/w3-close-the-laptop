"""Tests for per-chunk provenance and engine decoupling."""

from unittest.mock import MagicMock

import pytest

from steadydev.models import ChangedFile, FindingCategory, ReviewPacket
from steadydev.ollama_client import OllamaClient
from steadydev.reviewer import Reviewer


@pytest.fixture
def sample_packet() -> ReviewPacket:
    return ReviewPacket(
        packet_id="pkt-prov-001",
        timestamp_utc="2026-10-23T19:00:00Z",
        repo_name="w3-close-the-laptop",
        session_intention="Test chunk provenance",
        changed_files=[
            ChangedFile(
                path="src/file_1.py",
                status="modified",
                diff="@@ -1,5 +1,5 @@\n-def f1(): pass\n+def f1(): return 'v1'\n" * 40,
            ),
            ChangedFile(
                path="src/file_2.py",
                status="modified",
                diff="@@ -1,5 +1,5 @@\n-def f2(): pass\n+def f2(): return 'v2'\n" * 40,
            ),
        ],
    )


def test_chunk_provenance_records_fallback_cascade(sample_packet: ReviewPacket) -> None:
    """A fallback from primary to fallback model must record both attempts in chunk provenance."""
    mock_client = MagicMock(spec=OllamaClient)

    # Primary model (gemma) returns malformed json
    # Fallback model (qwen) returns valid json with finding
    def fake_chat(model: str, **kwargs):
        if model == "gemma3:4b":
            return {
                "content": '{"status": "incomplete...',  # malformed
                "model": "gemma3:4b",
                "done_reason": "length",
                "total_duration_ms": 120.0,
                "prompt_eval_count": 2000,
                "eval_count": 15,
            }
        elif model == "qwen2.5-coder:3b":
            return {
                "content": '{"status": "findings_detected", "findings": [{"locator": "src/file_1.py:1", "category": "needs_judgment", "description": "Documentation mismatch"}], "closing_summary": "Done", "restart_note": "Resume tomorrow"}',
                "model": "qwen2.5-coder:3b",
                "done_reason": "stop",
                "total_duration_ms": 110.0,
                "prompt_eval_count": 1700,
                "eval_count": 140,
            }
        return {}

    mock_client.chat.side_effect = fake_chat
    reviewer = Reviewer(ollama_client=mock_client)

    result = reviewer.review(
        sample_packet,
        model_name="gemma3:4b",
        fallback_model_name="qwen2.5-coder:3b",
        workflow_timeout_seconds=30.0,
    )

    assert len(result.chunk_provenance) >= 1
    chunk_1 = result.chunk_provenance[0]
    assert chunk_1.chunk_index == 1
    assert len(chunk_1.attempts) == 2

    # Attempt 1: Gemma failed schema/truncated
    att_1 = chunk_1.attempts[0]
    assert att_1.model == "gemma3:4b"
    assert att_1.outcome == "schema_invalid"
    assert att_1.input_tokens == 2000
    assert att_1.output_tokens == 15
    assert att_1.done_reason == "length"

    # Attempt 2: Qwen succeeded
    att_2 = chunk_1.attempts[1]
    assert att_2.model == "qwen2.5-coder:3b"
    assert att_2.outcome == "success"
    assert att_2.input_tokens == 1700
    assert att_2.output_tokens == 140
    assert att_2.done_reason == "stop"

    # Resolved engine
    assert chunk_1.resolved_engine == "qwen2.5-coder:3b"

    # Finding decoupling check
    assert len(result.findings) >= 1
    f = result.findings[0]
    assert f.category == FindingCategory.NEEDS_JUDGMENT
    assert f.engine == "qwen2.5-coder:3b"


def test_chunk_provenance_records_timeout_fallback(sample_packet: ReviewPacket) -> None:
    """When workflow deadline is exceeded, chunk provenance must record timeout_fallback."""
    reviewer = Reviewer()
    # Call review with an expired or 0-second deadline
    result = reviewer.review(
        sample_packet,
        model_name="gemma3:4b",
        workflow_timeout_seconds=0.0001,
    )

    assert len(result.chunk_provenance) >= 1
    for cp in result.chunk_provenance:
        assert cp.resolved_engine == "baseline-checklist"
        assert cp.fallback_reason == "timeout_fallback"
        for f in result.findings:
            assert f.engine == "baseline-checklist"
