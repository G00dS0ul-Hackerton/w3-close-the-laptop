"""Predeclared Stage C verification probe comparing baseline vs. local model on frozen cases.

Strict limits:
- Plain ASCII console output (P-4)
- 2 frozen cases: t02_mismatch.json (Case 1) and t01_clean.json (Case 2)
- At most 4 real model requests TOTAL (P-9: unload after each call)
- 3-layer evaluation per C-4
"""

import datetime
import json
import pathlib
import sys
import time

repo_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "src"))

from eval.run_eval import evaluate_layers  # type: ignore
from steadydev.baseline import ChecklistBaseline  # type: ignore
from steadydev.models import ReviewPacket  # type: ignore
from steadydev.ollama_client import OllamaClient  # type: ignore
from steadydev.reviewer import Reviewer  # type: ignore


def main() -> int:
    print("-" * 72)
    print("SteadyDev Stage C Verification Probe")
    print("-" * 72)

    fixtures_dir = repo_root / "eval" / "fixtures"
    t02_path = fixtures_dir / "t02_mismatch.json"
    t01_path = fixtures_dir / "t01_clean.json"

    with open(t02_path, encoding="utf-8") as f:
        pkt_case1 = ReviewPacket.model_validate(json.load(f))
    with open(t01_path, encoding="utf-8") as f:
        pkt_case2 = ReviewPacket.model_validate(json.load(f))

    cases = [
        ("Case 1 (Mismatch)", pkt_case1),
        ("Case 2 (Clean Negative)", pkt_case2),
    ]

    baseline = ChecklistBaseline()
    client = OllamaClient()

    # Pre-probe unload
    client.cancel_active()

    results: dict = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "baseline": {},
        "model_qwen": {},
    }

    # 1. Approach A: Baseline
    print("\n--- Approach A: ChecklistBaseline (0 model calls) ---")
    for name, pkt in cases:
        t0 = time.perf_counter()
        res = baseline.evaluate(pkt)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        eval_3layer = evaluate_layers(
            packet_id=pkt.packet_id,
            findings=[f.model_dump() for f in res.findings],
            retired_ids=res.retired_finding_ids,
            summary=res.closing_summary,
            restart_note=res.restart_note,
            review_status=res.status,
            error=res.error,
        )

        results["baseline"][pkt.packet_id] = {
            "name": name,
            "status": res.status,
            "findings_count": len(res.findings),
            "findings": [f.model_dump() for f in res.findings],
            "closing_summary": res.closing_summary,
            "restart_note": res.restart_note,
            "elapsed_ms": elapsed_ms,
            "eval_3layer": eval_3layer,
        }

        print(
            f"[{name}] status={res.status} findings={len(res.findings)} time={elapsed_ms:.2f}ms"
        )
        print(f"  L1 Findings : {eval_3layer['layer1_findings']['screening_verdict']}")
        print(f"  L2 Summary  : {eval_3layer['layer2_summary']['screening_verdict']}")
        print(f"  L3 Restart  : {eval_3layer['layer3_restart']['screening_verdict']}")
        print(f"  Restart Note: {res.restart_note}")

    # 2. Approach B: Local Open-Weight Model (qwen2.5-coder:3b)
    # Strict cap: 1 call per case = 2 calls total
    model_name = "qwen2.5-coder:3b"
    reviewer = Reviewer(ollama_client=client, baseline=baseline)

    print(f"\n--- Approach B: Local Model ({model_name}) (Strict Cap: 2 calls) ---")
    for name, pkt in cases:
        print(f"\nExecuting {name} with {model_name}...")
        t0 = time.perf_counter()
        res = reviewer.review(
            packet=pkt,
            model_name=model_name,
            use_baseline_fallback=False,
            workflow_timeout_seconds=180.0,
        )
        wall_s = time.perf_counter() - t0

        eval_3layer = evaluate_layers(
            packet_id=pkt.packet_id,
            findings=[f.model_dump() for f in res.findings],
            retired_ids=res.retired_finding_ids,
            summary=res.closing_summary,
            restart_note=res.restart_note,
            review_status=res.status,
            error=res.error,
        )

        results["model_qwen"][pkt.packet_id] = {
            "name": name,
            "status": res.status,
            "findings_count": len(res.findings),
            "findings": [f.model_dump() for f in res.findings],
            "closing_summary": res.closing_summary,
            "restart_note": res.restart_note,
            "wall_s": wall_s,
            "timing_ms": res.timing_ms,
            "eval_3layer": eval_3layer,
            "error": res.error,
        }

        print(
            f"[{name}] status={res.status} findings={len(res.findings)} wall={wall_s:.2f}s"
        )
        print(f"  L1 Findings : {eval_3layer['layer1_findings']['screening_verdict']}")
        print(f"  L2 Summary  : {eval_3layer['layer2_summary']['screening_verdict']}")
        print(f"  L3 Restart  : {eval_3layer['layer3_restart']['screening_verdict']}")
        print(f"  Summary     : {res.closing_summary}")
        print(f"  Restart Note: {res.restart_note}")
        for f in res.findings:
            print(f"    * [{f.category.value}] {f.locator}: {f.description}")

        # P-9: Mandatory model unload immediately after each trial
        print(f"Unloading {model_name} to free RAM...")
        client.unload_model(model_name)
        time.sleep(1.0)

    # Save receipt
    results_dir = repo_root / "eval" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    out_file = results_dir / "stage_c_receipt.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 72)
    print("Stage C Probe Complete. Receipt saved to eval/results/stage_c_receipt.json")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
