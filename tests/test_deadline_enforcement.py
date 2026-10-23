"""Tests for active workflow deadline enforcement during model execution."""

from unittest.mock import MagicMock

import pytest

from steadydev.models import ChangedFile, ReviewPacket
from steadydev.ollama_client import OllamaClient, OllamaTimeoutError
from steadydev.reviewer import Reviewer


@pytest.fixture
def multi_file_packet() -> ReviewPacket:
    return ReviewPacket(
        packet_id="pkt-test-deadline-001",
        timestamp_utc="2026-10-23T19:00:00Z",
        repo_name="w3-close-the-laptop",
        session_intention="Test deadline enforcement",
        changed_files=[
            ChangedFile(
                path="src/file_a.py",
                status="modified",
                diff="@@ -1,5 +1,5 @@\n-def a(): pass\n+def a(): return 1\n" * 50,
            ),
            ChangedFile(
                path="src/file_b.py",
                status="modified",
                diff="@@ -1,5 +1,5 @@\n-def b(): pass\n+def b(): return 2\n" * 50,
            ),
        ],
        check_receipts=[],
        prior_findings=[],
    )


def test_ollama_client_chat_accepts_and_enforces_request_timeout() -> None:
    """OllamaClient.chat() must accept a request-level timeout override."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {
            "content": '{"status": "clean", "findings": [], "closing_summary": "ok", "restart_note": "none"}'
        },
        "done_reason": "stop",
        "total_duration": 1_000_000,
        "load_duration": 100_000,
        "prompt_eval_duration": 400_000,
        "eval_duration": 500_000,
        "prompt_eval_count": 100,
        "eval_count": 20,
    }
    mock_client.post.return_value = mock_resp

    client = OllamaClient(client=mock_client)
    res = client.chat(
        model="gemma3:4b",
        messages=[{"role": "user", "content": "hi"}],
        timeout=5.0,
    )
    assert res["done_reason"] == "stop"
    # Verify timeout was passed to underlying client post call
    _, kwargs = mock_client.post.call_args
    assert kwargs.get("timeout") == 5.0


def test_reviewer_passes_remaining_budget_as_timeout_to_chat(
    multi_file_packet: ReviewPacket,
) -> None:
    """Reviewer must compute remaining workflow budget and pass it to chat()."""
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.chat.return_value = {
        "content": '{"status": "clean", "findings": [], "closing_summary": "ok", "restart_note": "none"}',
        "model": "gemma3:4b",
        "done_reason": "stop",
        "total_duration_ms": 100.0,
        "load_duration_ms": 10.0,
        "prompt_eval_duration_ms": 40.0,
        "eval_duration_ms": 50.0,
        "prompt_eval_count": 100,
        "eval_count": 20,
    }
    reviewer = Reviewer(ollama_client=mock_client)

    reviewer.review(
        multi_file_packet,
        model_name="gemma3:4b",
        workflow_timeout_seconds=10.0,
    )

    assert mock_client.chat.called
    for call in mock_client.chat.call_args_list:
        _, kwargs = call
        passed_timeout = kwargs.get("timeout")
        assert passed_timeout is not None
        assert 0.0 < passed_timeout <= 10.0


def test_reviewer_aborts_on_mid_call_timeout_and_unloads_model(
    multi_file_packet: ReviewPacket,
) -> None:
    """When a model call times out mid-flight, reviewer must unload model and fallback to baseline."""
    mock_client = MagicMock(spec=OllamaClient)
    # Simulate a mid-call timeout exception
    mock_client.chat.side_effect = OllamaTimeoutError(
        "Request timed out during inference"
    )
    mock_client.unload_model = MagicMock()

    reviewer = Reviewer(ollama_client=mock_client)

    result = reviewer.review(
        multi_file_packet,
        model_name="gemma3:4b",
        fallback_model_name="qwen2.5-coder:3b",
        workflow_timeout_seconds=5.0,
    )

    # Must have attempted to unload model via Pattern P-9
    assert mock_client.unload_model.called
    # Result must gracefully fallback to baseline safety floor
    assert result.status in ("clean", "findings_detected", "fallback_baseline")
    assert result.closing_summary != ""
    assert result.restart_note != ""
