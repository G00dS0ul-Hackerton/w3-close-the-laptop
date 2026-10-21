"""Regression tests for evaluation harness grading, failure handling, and code provenance."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root and eval directory to sys.path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "src"))

from eval.run_eval import (
    compute_code_manifest_provenance,
    evaluate_layers,
    run_evaluation,
)
from steadydev.models import ReviewResult


def test_evaluate_layers_failed_review_states() -> None:
    """A parse_error or unavailable review must produce FAILED_REVIEW across all 3 layers."""
    for bad_status in ["parse_error", "unavailable", "fallback_baseline"]:
        # Test across canonical cases
        for pkt_id in [
            "pkt-eval-t01",
            "pkt-eval-t02",
            "pkt-eval-t03",
            "pkt-eval-t04",
            "pkt-eval-t05",
            "pkt-eval-t06a",
            "pkt-eval-t06b",
        ]:
            res = evaluate_layers(
                packet_id=pkt_id,
                findings=[],
                retired_ids=[],
                summary="",
                restart_note="",
                review_status=bad_status,
                error="Model output was malformed or unavailable",
            )
            assert res["layer1_findings"]["screening_verdict"] == "FAILED_REVIEW"
            assert res["layer2_summary"]["screening_verdict"] == "FAILED_REVIEW"
            assert res["layer3_restart"]["screening_verdict"] == "FAILED_REVIEW"

            # Must NEVER award positive credit on failed review!
            assert res["layer1_findings"]["screening_verdict"] != "CORRECT_CLEAN"
            assert (
                res["layer1_findings"]["screening_verdict"]
                != "CORRECT_DEFERRAL_HONORED"
            )
            assert (
                res["layer1_findings"]["screening_verdict"] != "CORRECT_NON_RETIREMENT"
            )
            assert res["layer1_findings"]["screening_verdict"] != "MISSED_GAP"
            assert res["layer2_summary"]["screening_verdict"] != "FACTUAL_ACCOUNTING"
            assert res["layer3_restart"]["screening_verdict"] != "ACTIONABLE_CONTINUITY"


def test_evaluate_layers_empty_summary_and_restart() -> None:
    """Empty closing summary or restart note must not receive default praise."""
    res = evaluate_layers(
        packet_id="pkt-eval-t01",
        findings=[],
        retired_ids=[],
        summary="",
        restart_note="   ",
        review_status="clean",
        error=None,
    )
    assert res["layer2_summary"]["screening_verdict"] == "EMPTY_SUMMARY"
    assert res["layer3_restart"]["screening_verdict"] == "EMPTY_RESTART_NOTE"
    assert res["layer2_summary"]["screening_verdict"] != "FACTUAL_ACCOUNTING"
    assert res["layer3_restart"]["screening_verdict"] != "ACTIONABLE_CONTINUITY"


def test_t05_deferral_positive_verification() -> None:
    """T05 requires valid status and positive evidence in summary/restart to honor deferral."""
    res = evaluate_layers(
        packet_id="pkt-eval-t05",
        findings=[],
        retired_ids=[],
        summary="Added user profile fields. Database migration is deferred.",
        restart_note="Resume database migration tomorrow.",
        review_status="clean",
        error=None,
    )
    assert res["layer1_findings"]["screening_verdict"] == "CORRECT_DEFERRAL_HONORED"
    assert res["layer2_summary"]["screening_verdict"] == "FACTUAL_ACCOUNTING"
    assert res["layer3_restart"]["screening_verdict"] in {
        "ACTIONABLE_CONTINUITY",
        "HIGH_CONTINUITY",
    }


def test_provenance_rejects_empty_git_tree() -> None:
    """Code manifest provenance must produce a valid non-empty hash and not the Git empty tree SHA."""
    EMPTY_GIT_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    prov = compute_code_manifest_provenance(base_dir=str(repo_root))
    assert prov["manifest_sha256"] != EMPTY_GIT_TREE_SHA
    assert len(prov["manifest_sha256"]) == 64
    assert prov["manifest_file_count"] >= 10
    assert any("reviewer.py" in f["path"] for f in prov["files"])


def test_receipt_cold_probe_is_distinct_from_warm_t01() -> None:
    """Evaluation runner produces distinct records for cold_probe and warm pkt-eval-t01."""
    with (
        patch("eval.run_eval.OllamaClient") as mock_client_cls,
        patch("eval.run_eval.Reviewer") as mock_reviewer_cls,
        patch("eval.run_eval.wait_for_unload", return_value=True),
    ):
        mock_client = MagicMock()
        mock_client.get_version.return_value = "0.40.6"
        mock_client.get_running_models.return_value = [{"model": "qwen2.5-coder:3b"}]
        mock_client_cls.return_value = mock_client

        mock_reviewer = MagicMock()
        cold_res = ReviewResult(
            packet_id="pkt-eval-t01",
            status="clean",
            model_name="test-model",
            findings=[],
            timing_ms={"load_duration_ms": 5000.0, "total_duration_ms": 7000.0},
            closing_summary="Cold run",
            restart_note="Ready",
        )
        warm_res = ReviewResult(
            packet_id="pkt-eval-t01",
            status="clean",
            model_name="test-model",
            findings=[],
            timing_ms={"load_duration_ms": 0.0, "total_duration_ms": 2000.0},
            closing_summary="Warm run",
            restart_note="Ready",
        )
        mock_reviewer.review.side_effect = [cold_res, warm_res] * 10
        mock_reviewer_cls.return_value = mock_reviewer

        t01_path = str(repo_root / "eval" / "fixtures" / "t01_clean.json")
        res = run_evaluation(
            prompt_variant_name="tuned",
            fixture_glob=t01_path,
            save_receipt=False,
        )

        for model_name in ["qwen2.5-coder:3b", "gemma3:4b"]:
            m_res = res["models"][model_name]
            cold = m_res["cold_probe"]
            warm_t01 = m_res["cases"]["pkt-eval-t01"]
            assert cold["trial_type"] == "COLD_PROBE"
            assert warm_t01["trial_type"] == "WARM_RUN"
            assert cold is not warm_t01
            assert cold["load_ms"] != warm_t01["load_ms"]
