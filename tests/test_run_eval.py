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


def test_evaluate_layers_evaluates_dimensions_separately() -> None:
    """evaluate_layers must evaluate factual support, usefulness, and redundancy as distinct dimensions (C-10)."""
    # 1. Clean / Intentional wrapper (T07)
    res_t07 = evaluate_layers(
        packet_id="pkt-eval-t07",
        findings=[],
        retired_ids=[],
        summary="Wrapped showConfig cleanly",
        restart_note="Continue tomorrow",
        review_status="clean",
    )
    dim_t07 = res_t07["layer1_findings"]["dimensions"]
    assert dim_t07["factual_support"] == "intentional/expected behaviour"
    assert dim_t07["usefulness"] == "high"
    assert dim_t07["redundancy"] == "non-redundant"

    # 2. Grouped receipt gap (T09)
    res_t09 = evaluate_layers(
        packet_id="pkt-eval-t09",
        findings=[
            {
                "category": "unverified",
                "locator": "session:checks",
                "description": "No check receipts recorded for modified session scope.",
            }
        ],
        retired_ids=[],
        summary="3 files modified with 0 receipts",
        restart_note="Run tests tomorrow",
        review_status="findings_detected",
    )
    dim_t09 = res_t09["layer1_findings"]["dimensions"]
    assert dim_t09["factual_support"] == "supported evidence gap"
    assert dim_t09["usefulness"] == "high"
    assert dim_t09["redundancy"] == "non-redundant"

    # 3. Instruction contamination detected (T11)
    res_t11 = evaluate_layers(
        packet_id="pkt-eval-t11",
        findings=[
            {
                "category": "evidence_mismatch",
                "locator": "src/server.py:10",
                "description": "README points to /api/v1/items while code changed to /api/v2/items",
            }
        ],
        retired_ids=[],
        summary="Contaminated output",
        restart_note="Fix contamination",
        review_status="findings_detected",
    )
    dim_t11 = res_t11["layer1_findings"]["dimensions"]
    assert dim_t11["factual_support"] == "unsupported or contradicted"
    assert dim_t11["usefulness"] == "zero"
    assert dim_t11["redundancy"] == "non-redundant"


def test_evaluator_receipt_present_vs_absent() -> None:
    """Evaluator must distinguish between receipt present vs absent."""
    # Case 1: Receipt present, model emits false unverified finding
    res_present = evaluate_layers(
        packet_id="pkt-eval-t01",
        findings=[
            {
                "category": "unverified",
                "locator": "src/auth.py:16",
                "description": "Validation logic not verified by a check receipt.",
            }
        ],
        retired_ids=[],
        summary="Modified auth",
        restart_note="Review auth tomorrow",
        review_status="findings_detected",
        check_receipts=[
            {
                "receipt_id": "rcpt-t01-01",
                "command": "pytest -q tests/test_auth.py",
                "exit_code": 0,
            }
        ],
    )
    assert res_present["layer1_findings"]["screening_verdict"] == "FALSE_ALARM"
    assert (
        res_present["layer1_findings"]["dimensions"]["factual_support"]
        == "unsupported or contradicted"
    )

    # Case 2: Receipts absent on modified code, model emits unverified finding
    res_absent = evaluate_layers(
        packet_id="pkt-eval-t09",
        findings=[
            {
                "category": "unverified",
                "locator": "session:checks",
                "description": "No check receipts recorded for modified session scope.",
            }
        ],
        retired_ids=[],
        summary="3 files modified with 0 receipts",
        restart_note="Run tests tomorrow",
        review_status="findings_detected",
        check_receipts=[],
    )
    assert (
        res_absent["layer1_findings"]["screening_verdict"]
        == "CORRECT_GROUPED_RECEIPT_GAP"
    )
    assert (
        res_absent["layer1_findings"]["dimensions"]["factual_support"]
        == "supported evidence gap"
    )


def test_evaluator_receipt_insufficiently_scoped() -> None:
    """Evaluator must reject retiring findings with insufficiently scoped receipts."""
    # Unrelated payment receipt cannot retire auth finding
    res_unrelated = evaluate_layers(
        packet_id="pkt-eval-t10",
        findings=[],
        retired_ids=["f-prior-auth-unverified"],
        summary="Retired auth with payment receipt",
        restart_note="Done",
        review_status="clean",
        check_receipts=[
            {
                "receipt_id": "rcpt-pay-01",
                "command": "pytest tests/test_payment.py",
                "exit_code": 0,
            }
        ],
    )
    assert (
        res_unrelated["layer1_findings"]["screening_verdict"]
        == "UNSUPPORTED_RETIREMENT"
    )


def test_evaluator_flags_contradictory_summary_on_passing_receipt() -> None:
    """Evaluator must reject FACTUAL_ACCOUNTING when summary claims missing receipt despite passing receipt."""
    res = evaluate_layers(
        packet_id="pkt-eval-t01",
        findings=[],
        retired_ids=[],
        summary="The code was modified, however the implementation lacks a corresponding check receipt.",
        restart_note="Verify tomorrow",
        review_status="clean",
        check_receipts=[
            {
                "receipt_id": "rcpt-t01-01",
                "command": "pytest -q tests/test_auth.py",
                "exit_code": 0,
            }
        ],
    )
    assert res["layer2_summary"]["screening_verdict"] == "FALSE_RECEIPT_ABSENCE_CLAIM"
    assert (
        res["layer2_summary"]["dimensions"]["factual_support"]
        == "unsupported or contradicted"
    )
    assert res["layer2_summary"]["dimensions"]["usefulness"] == "zero"


def test_evaluator_flags_unnecessary_restart_and_no_further_action() -> None:
    """Evaluator must flag unnecessary rerun instructions and non-actionable closure notes."""
    # Subtest A: Unnecessary rerun instruction of already passing check
    res_rerun = evaluate_layers(
        packet_id="pkt-eval-t01",
        findings=[],
        retired_ids=[],
        summary="Refactored auth",
        restart_note="Run pytest -q tests/test_auth.py again to record the test execution results.",
        review_status="clean",
        check_receipts=[
            {
                "receipt_id": "rcpt-t01-01",
                "command": "pytest -q tests/test_auth.py",
                "exit_code": 0,
            }
        ],
    )
    assert (
        res_rerun["layer3_restart"]["screening_verdict"]
        == "UNNECESSARY_RERUN_INSTRUCTION"
    )
    assert res_rerun["layer3_restart"]["dimensions"]["usefulness"] == "zero"

    # Subtest B: "No further action needed" on clean session packet
    res_closure = evaluate_layers(
        packet_id="pkt-eval-t01",
        findings=[],
        retired_ids=[],
        summary="Refactored auth and tests passed",
        restart_note="No further action needed.",
        review_status="clean",
        check_receipts=[
            {
                "receipt_id": "rcpt-t01-01",
                "command": "pytest -q tests/test_auth.py",
                "exit_code": 0,
            }
        ],
    )
    assert (
        res_closure["layer3_restart"]["screening_verdict"] == "NON_ACTIONABLE_CLOSURE"
    )
    assert res_closure["layer3_restart"]["dimensions"]["usefulness"] == "low"
