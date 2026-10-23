"""Controlled Diagnostic Experiment: num_ctx=2048 vs num_ctx=4096 with Gemma 3 4B.

Measures memory, latency, token count, done_reason, and schema validity
for Chunk 1 diff context (~2,000 prompt tokens) to empirically verify
context truncation vs schema completion.
"""

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import time

# Ensure ASCII safe output on Windows (Pattern P-4)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from steadydev.models import ChangedFile, ReviewPacket
from steadydev.ollama_client import OllamaClient
from steadydev.packet import format_packet_for_prompt
from steadydev.reviewer import Reviewer, strip_markdown_fences


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_uint64),
        ("ullAvailPhys", ctypes.c_uint64),
        ("ullTotalPageFile", ctypes.c_uint64),
        ("ullAvailPageFile", ctypes.c_uint64),
        ("ullTotalVirtual", ctypes.c_uint64),
        ("ullAvailVirtual", ctypes.c_uint64),
        ("ullAvailExtendedVirtual", ctypes.c_uint64),
    ]


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def get_system_memory() -> tuple[float, int]:
    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    avail_gb = stat.ullAvailPhys / (1024**3)
    return avail_gb, stat.dwMemoryLoad


def get_process_rss_mb() -> tuple[float, float]:
    pmc = PROCESS_MEMORY_COUNTERS_EX()
    pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
    ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.windll.kernel32.GetCurrentProcess(),
        ctypes.byref(pmc),
        ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX),
    )
    rss_mb = pmc.WorkingSetSize / (1024**2)
    peak_mb = pmc.PeakWorkingSetSize / (1024**2)
    return rss_mb, peak_mb


def build_chunk1_prompt() -> tuple[list[dict[str, str]], ReviewPacket]:
    cf1 = ChangedFile(
        path="desktop/lib/models/session_models.dart",
        status="modified",
        diff="""diff --git a/desktop/lib/models/session_models.dart b/desktop/lib/models/session_models.dart
--- a/desktop/lib/models/session_models.dart
+++ b/desktop/lib/models/session_models.dart
@@ -231,6 +231,7 @@ class ReviewResultData {
   final String restartNote;
   final List<String> retiredFindingIds;
   final String? error;
+  final bool unchangedSnapshot;
 
   ReviewResultData({
     required this.packetId,
@@ -242,6 +243,7 @@ class ReviewResultData {
     required this.restartNote,
     required this.retiredFindingIds,
     this.error,
+    this.unchangedSnapshot = false,
   });
 
   factory ReviewResultData.fromJson(Map<String, dynamic> json) {
@@ -264,6 +266,7 @@ class ReviewResultData {
           .map((e) => e.toString())
           .toList(),
       error: json['error'] as String?,
+      unchangedSnapshot: json['unchanged_snapshot'] as bool? ?? false,
     );
   }
 }""",
    )

    cf2 = ChangedFile(
        path="desktop/lib/widgets/steady_dev_scaffold.dart",
        status="modified",
        diff="""diff --git a/desktop/lib/widgets/steady_dev_scaffold.dart b/desktop/lib/widgets/steady_dev_scaffold.dart
--- a/desktop/lib/widgets/steady_dev_scaffold.dart
+++ b/desktop/lib/widgets/steady_dev_scaffold.dart
@@ -347,7 +347,11 @@ class _SteadyDevScaffoldState extends State<SteadyDevScaffold> {
             }
 
             _findings = mergedFindings;
-            _quietStatus = 'Checkpoint complete';
+            if (res.unchangedSnapshot) {
+              _quietStatus = 'Snapshot unchanged · Displaying current findings';
+            } else {
+              _quietStatus = 'Checkpoint complete';
+            }
             _activeEngineTier = res.modelTag;
             if (!_isNoteUserEdited && res.restartNote.isNotEmpty) {
               _restartNote = res.restartNote;
@@ -400,6 +404,18 @@ class _SteadyDevScaffoldState extends State<SteadyDevScaffold> {
     });
   }
 
+  Future<void> _handleTogglePause() async {
+    final nextPaused = !_isPaused;
+    setState(() => _isPaused = nextPaused);
+    try {
+      if (nextPaused) {
+        await widget.apiClient?.pauseSession(_repoPath);
+      } else {
+        await widget.apiClient?.resumeSession(_repoPath);
+      }
+    } catch (_) {}
+  }
+
   void _updateFindingStatus(FindingItem finding, FindingLifecycle status, String? reason) {
     setState(() {
       finding.lifecycle = status;""",
    )

    packet = ReviewPacket(
        packet_id="snap-f1b8fc321dbf-c1",
        timestamp_utc="2026-10-23T18:17:25Z",
        repo_name="w3-close-the-laptop",
        session_intention="Implement Milestone M4: quiet review scheduling with working-tree fingerprint deduplication, single-worker 409 concurrency gate, mid-flight staleness protection, and privacy-scrubbed opt-in Sentry AI agent tracing.",
        acceptance_criteria=[
            "Correct destination",
            "Mobile navigation",
            "No auth regressions",
        ],
        changed_files=[cf1, cf2],
        check_receipts=[],
        prior_findings=[],
        explicit_deferrals=[],
        truncated=False,
        omitted_files=[],
    )

    outline = [
        {"path": "desktop/lib/models/session_models.dart", "status": "modified"},
        {"path": "desktop/lib/widgets/steady_dev_scaffold.dart", "status": "modified"},
        {"path": "src/steadydev/ollama_client.py", "status": "modified"},
        {"path": "src/steadydev/reviewer.py", "status": "modified"},
    ]

    prompt_context = format_packet_for_prompt(packet, workspace_outline=outline)
    reviewer = Reviewer()
    messages = [
        {"role": "system", "content": reviewer.system_prompt},
        {
            "role": "user",
            "content": f"Review this session context chunk (1/4) and emit JSON:\n\n{prompt_context}",
        },
    ]
    return messages, packet


def run_trial(
    client: OllamaClient,
    model: str,
    messages: list[dict[str, str]],
    num_ctx: int,
    trial_name: str,
) -> dict:
    """Execute a single controlled trial measuring memory, latency, and tokens."""
    print(f"\n--- Starting {trial_name} (num_ctx={num_ctx}) ---")

    avail_gb, mem_load = get_system_memory()
    print(f"System memory: {avail_gb:.2f} GB available (Load: {mem_load}%)")
    if avail_gb < 1.5 or mem_load > 90:
        raise RuntimeError(
            f"Safety check triggered: System memory is too low ({avail_gb:.2f} GB avail, {mem_load}% load). Aborting."
        )

    initial_rss, initial_peak = get_process_rss_mb()
    start_wall = time.monotonic()

    try:
        raw_resp = client.chat(
            model=model,
            messages=messages,
            options={"num_ctx": num_ctx, "num_predict": 512},
            timeout=180.0,
        )
        elapsed_wall = time.monotonic() - start_wall
        end_rss, end_peak = get_process_rss_mb()
        client.unload_model(model)

        raw_text = raw_resp.get("content", "")
        done_reason = raw_resp.get("done_reason", "unknown")
        in_tokens = raw_resp.get("prompt_eval_count", 0)
        out_tokens = raw_resp.get("eval_count", 0)
        total_tokens = in_tokens + out_tokens
        prompt_eval_ms = raw_resp.get("prompt_eval_duration_ms", 0.0)
        eval_ms = raw_resp.get("eval_duration_ms", 0.0)
        total_model_ms = raw_resp.get("total_duration_ms", 0.0)

        cleaned_text = strip_markdown_fences(raw_text)
        is_json_valid = False
        is_schema_valid = False
        json_error = None
        parsed_json = None

        try:
            parsed_json = json.loads(cleaned_text)
            is_json_valid = True
            if isinstance(parsed_json, dict) and "findings" in parsed_json:
                is_schema_valid = True
            else:
                json_error = "Missing 'findings' key in response object"
        except json.JSONDecodeError as err:
            json_error = f"JSONDecodeError: {err}"

        findings_count = len(parsed_json.get("findings", [])) if is_schema_valid else 0

        return {
            "trial_name": trial_name,
            "num_ctx": num_ctx,
            "model": model,
            "done_reason": done_reason,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "total_tokens": total_tokens,
            "prompt_eval_ms": prompt_eval_ms,
            "eval_ms": eval_ms,
            "total_model_ms": total_model_ms,
            "wall_time_s": elapsed_wall,
            "initial_rss_mb": initial_rss,
            "peak_rss_mb": end_peak,
            "rss_delta_mb": end_rss - initial_rss,
            "is_json_valid": is_json_valid,
            "is_schema_valid": is_schema_valid,
            "findings_count": findings_count,
            "json_error": json_error,
        }

    except Exception as exc:
        elapsed_wall = time.monotonic() - start_wall
        end_rss, end_peak = get_process_rss_mb()
        client.unload_model(model)
        is_timeout = "timeout" in str(exc).lower()

        return {
            "trial_name": trial_name,
            "num_ctx": num_ctx,
            "model": model,
            "done_reason": "timeout" if is_timeout else "error",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "prompt_eval_ms": 0.0,
            "eval_ms": 0.0,
            "total_model_ms": 0.0,
            "wall_time_s": elapsed_wall,
            "initial_rss_mb": initial_rss,
            "peak_rss_mb": end_peak,
            "rss_delta_mb": end_rss - initial_rss,
            "is_json_valid": False,
            "is_schema_valid": False,
            "findings_count": 0,
            "json_error": str(exc),
        }


def print_and_save_report(results: list[dict], model: str):
    res1, res2 = results[0], results[1]
    print("\n" + "=" * 75)
    print("EXPERIMENTAL EVIDENCE COMPARISON")
    print("=" * 75)
    print(f"{'Metric':<32} | {'Trial 1 (2048)':<18} | {'Trial 2 (4096)':<18}")
    print("-" * 75)
    print(f"{'num_ctx limit':<32} | {res1['num_ctx']:<18} | {res2['num_ctx']:<18}")
    print(f"{'Input Tokens (prompt)':<32} | {res1['input_tokens']:<18} | {res2['input_tokens']:<18}")
    print(f"{'Output Tokens (eval)':<32} | {res1['output_tokens']:<18} | {res2['output_tokens']:<18}")
    print(f"{'Total Tokens':<32} | {res1['total_tokens']:<18} | {res2['total_tokens']:<18}")
    print(f"{'Ollama done_reason':<32} | {res1['done_reason']:<18} | {res2['done_reason']:<18}")
    print(f"{'Prompt Eval Time (s)':<32} | {res1['prompt_eval_ms']/1000.0:<18.2f} | {res2['prompt_eval_ms']/1000.0:<18.2f}")
    print(f"{'Generation Time (s)':<32} | {res1['eval_ms']/1000.0:<18.2f} | {res2['eval_ms']/1000.0:<18.2f}")
    print(f"{'Wall Clock Duration (s)':<32} | {res1['wall_time_s']:<18.2f} | {res2['wall_time_s']:<18.2f}")
    print(f"{'Peak Process RSS (MB)':<32} | {res1['peak_rss_mb']:<18.1f} | {res2['peak_rss_mb']:<18.1f}")
    print(f"{'JSON Parseable':<32} | {str(res1['is_json_valid']):<18} | {str(res2['is_json_valid']):<18}")
    print(f"{'Schema Valid':<32} | {str(res1['is_schema_valid']):<18} | {str(res2['is_schema_valid']):<18}")
    print(f"{'Findings Emitted':<32} | {res1['findings_count']:<18} | {res2['findings_count']:<18}")
    if res1["json_error"]:
        print(f"{'Trial 1 Error':<32} | {res1['json_error']}")
    if res2["json_error"]:
        print(f"{'Trial 2 Error':<32} | {res2['json_error']}")
    print("=" * 75)

    out_dir = Path("eval/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = out_dir / "context_experiment_receipt.json"

    receipt_data = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": model,
        "trials": results,
    }

    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(receipt_data, f, indent=2)
    print(f"\nExperiment receipt saved to: {receipt_path}")


def main():
    print("=" * 75)
    print("STEADYDEV CONTROLLED CONTEXT SIZING EXPERIMENT")
    print("Hypothesis Verification: num_ctx=2048 vs num_ctx=4096")
    print("Model: gemma3:4b (CPU loopback)")
    print("=" * 75)

    # Check if receipt already exists or if we should run
    receipt_path = Path("eval/results/context_experiment_receipt.json")
    if receipt_path.exists():
        try:
            with open(receipt_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if "trials" in cached and len(cached["trials"]) == 2:
                print("Found existing experiment receipt:")
                print_and_save_report(cached["trials"], cached.get("model", "gemma3:4b"))
                return
        except Exception:
            pass

    client = OllamaClient()
    try:
        ver = client.get_version()
        print(f"Connected to Ollama daemon (version: {ver})")
    except Exception as exc:
        print(f"ERROR: Cannot connect to Ollama: {exc}")
        sys.exit(1)

    messages, packet = build_chunk1_prompt()
    model = "gemma3:4b"
    results = []

    res1 = run_trial(client, model, messages, num_ctx=2048, trial_name="Trial 1 (num_ctx=2048)")
    results.append(res1)
    print(f"Trial 1 finished: in_tok={res1['input_tokens']}, out_tok={res1['output_tokens']}, done_reason={res1['done_reason']}, valid={res1['is_schema_valid']}")

    time.sleep(3)

    res2 = run_trial(client, model, messages, num_ctx=4096, trial_name="Trial 2 (num_ctx=4096)")
    results.append(res2)
    print(f"Trial 2 finished: in_tok={res2['input_tokens']}, out_tok={res2['output_tokens']}, done_reason={res2['done_reason']}, valid={res2['is_schema_valid']}")

    print_and_save_report(results, model)


if __name__ == "__main__":
    main()
