# SteadyDev (Close the Laptop)

> **"You don't have to finish everything today. You just need to know where you stand and how to continue tomorrow."**

SteadyDev is a local-first, open-weight AI companion designed to help developers end their work sessions with clarity. Rather than pressuring you to clear an endless backlog or hovering over every keystroke, SteadyDev quietly compares your session goals, code changes, and verification checks. It highlights potential gaps with supporting evidence, evaluates doc drift, and generates an editable closing summary with a durable restart note for tomorrow.

Built for the **Hacktoberfest Open-Source AI Challenge 2026 (Week 3: Slow and Steady)**.
- **Repository:** https://github.com/G00dS0ul-Hackerton/w3-close-the-laptop
- **License:** MIT License (2026 G00dS0ul-Hackerton)

---

## Core Philosophy

SteadyDev maintains a strict four-way separation of session state:
- **Changed:** What files and functions were modified during the session.
- **Checked:** What tests, typechecks, or viewports were explicitly verified with receipts.
- **Uncertain / Needs Judgment:** What remains unverified (not proof of a defect, but an unrecorded check).
- **Deferred:** What you deliberately set aside for the next session.

---

## Architecture & Milestones

In accordance with workspace guidelines, milestones are ordered chronologically (M1 to M6):

### Milestone M1 — Real Local Reviewer Feasibility (Completed)
Milestone M1 established the feasibility of local open-weight code reviewing on CPU using Ollama before presentation UI work.
- **Deterministic Baseline (<5 ms):** Zero-LLM reference engine verifying criteria, receipts, and deferral markers.
- **Sequential Model Evaluation:** Evaluated `gemma3:4b` vs `qwen2.5-coder:3b` across canonical test fixtures on CPU.
- **Bounded Packet Security:** Strict allowlisting, diff truncation (max 400 lines / 8 KB), and XML delimiter data-inertia framing against prompt injection.
- **Deterministic Locator Validation:** 4-step post-processing guard preventing locator forgery and directory traversal.
- **Graceful Error Handling:** Safe degradation on Ollama outages or malformed outputs without crashing.

---

### Milestone M2 — Real Flutter Vertical Slice & Loopback Engine (Completed)
Milestone M2 connected the native Flutter Windows desktop application to the local Python review engine over an authenticated loopback IPC boundary (`127.0.0.1:0`), executing real inference on CPU.
- **Native Flutter Desktop Client (`desktop/`):**
  - **Modular Architecture:** Ultra-thin `main.dart` (14 lines) and `app.dart` (37 lines) with the desktop shell extracted into `lib/widgets/steady_dev_scaffold.dart`.
  - **Green Brand System:** Visual contract implemented from `prototype.html` in Light (`#f5f8f4`) and Dark (`#001a06`) themes with verified WCAG AA contrast (>4.5:1 text, >3:1 controls).
  - **Three Core Views:** Session view (intention card & checklist), Quiet Audit view (lifecycle filters: Open, Deferred, Resolved, Dismissed), and Closing view (restart note editor).
  - **Local Theme Persistence:** Local JSON preference storage in `%LOCALAPPDATA%\SteadyDev\preferences.json`.
- **Python Loopback IPC Server (`src/steadydev/server.py`):**
  - Standard library `ThreadingHTTPServer` bound to ephemeral loopback (`127.0.0.1:0`).
  - Per-launch 256-bit token authentication (`Authorization: Bearer <token>`).
  - Stdin EOF watchdog thread ensuring zero-zombie child process termination when the desktop window closes.
- **Safe Git Snapshot Collector (`src/steadydev/git_collector.py`):**
  - Live Git diff collector enforcing repository boundaries and rejecting directory traversal (`..`).
  - Multi-variant privacy redaction: automatically scrubs Windows paths, usernames, emojis, and sensitive tokens.

---

### Milestone M3 — Durable Stopping and Restart (Completed)
Milestone M3 established atomic local SQLite persistence ensuring session intentions, criteria, evidence, and restart notes remain trustworthy across app closures and machine restarts.
- **Transactional SQLite Store (`src/steadydev/store.py`):**
  - Schema V4 with foreign keys, 5000ms busy timeout, and Write-Ahead Logging (WAL) with TRUNCATE mode on shutdown.
  - Safe data location in `%LOCALAPPDATA%\SteadyDev\steadydev.db`.
- **Deterministic Working-Tree Fingerprinting:**
  - 16-character composite SHA-256 over HEAD commit SHA, unstaged diff hash, and untracked file entries up to 32 KB.
  - Mid-flight freshness fence: detects concurrent file modifications during inference and rejects stale results with `HTTP 409 Conflict`.
- **Durable Restart Note:**
  - Restart notes edited by the developer are marked `is_note_user_edited=1`, guaranteeing that background reviews or restarts never overwrite custom notes.

---

### Milestone M4 — Quiet Checkpoints & Sentry Agent Tracing (Completed)
Milestone M4 added intelligent review orchestration, local diagnostics, and opt-in observability via Sentry AI Agent Tracing.
- **Map-Reduce Review & Diff Distillation:**
  - Two-tier chunking splits multi-file changes into $\le 2,500$-character packets, keeping prompts within CPU context budgets.
  - Diff distillation strips repetitive file noise while preserving signatures, branch logic, and hunk headers.
- **Physical Inference Cancellation & RAM Unloading:**
  - Stop action physically severs the underlying HTTP transport socket and sends `keep_alive: 0` to Ollama (`P-9`), preventing dual-model residency and eliminating RAM thrashing.
- **Sentry AI Agent Tracing (15 Spans):**
  - Instruments the complete review lifecycle: `steadydev.review` root transaction, 5 `gen_ai.chat` spans, `chunk.prepare`, `validation.schema_check`, `reconciliation.reconcile`, and `persistence.store`.
  - Strict privacy allowlists (`ALLOWED_SPAN_OPS`, `ALLOWED_SPAN_DATA_KEYS`) and wire-byte scrubbers guarantee that zero source code diffs, prompts, or personal paths leave the machine.
  - Cross-process trace continuation headers (`sentry-trace`, `baggage`, `X-Run-ID`) correlate desktop actions to engine spans.
- **Local Diagnostics Independence (D-12):**
  - Local `DiagnosticsDialog` operates 100% offline, displaying pipeline phases and chunk attempt metrics even when Sentry is disabled. Trace ID generation (`staged_local`) is decoupled from verified delivery (`verified_delivered`).
- **Snapshot Deduplication:**
  - Unchanged code returns in <15 ms (a 106.5x speedup: 599 ms vs 63.8 s) without triggering redundant model inference.

---

### Milestone M5 — Conditional Tinker Experiment & Cut Line (Completed)
Milestone M5 evaluated whether cloud LoRA fine-tuning using Thinking Machines' Tinker API could improve factual evidence-grounding over the deterministic baseline and local models.
- **Cloud LoRA Experiment:** Executed Gate 3 cloud LoRA training on `Qwen/Qwen3.5-4B` over 24 synthetic grounding pairs (18 optimizer steps, 55,276 tokens, $0.0221 USD promo credits spent, $0.00 out of pocket).
- **Empirical Cut Line:** The fine-tuned model yielded a +0.0 pp delta on held-out test data, missing the required +25.0 pp threshold.
- **Disciplined Execution:** In strict accordance with the contest build plan cut line, this honest negative result was recorded, the sponsor category was omitted from the submission, and SteadyDev's 100% local-first architecture on Gemma and Qwen was preserved.

---

### Milestone M6 — Evaluation, Release Handoff & Submission Verification (Completed)
Milestone M6 validated final release configuration, executed full test regression suites, and prepared submission evidence.
- **Full Test Suite Passing:**
  - **Python Review Engine:** 168/168 unit and integration tests passing (`pytest -q` in ~3.4 mins).
  - **Flutter Desktop Client:** 38/38 widget, theme, and correlation tests passing (`flutter test` in ~26s).
  - **Boundary Verification Matrix:** 7/7 scenarios passing (`verify_m4_trace_matrix.py` in ~1.7s).
- **Honest CPU Benchmark Disclosed:**
  - Multi-chunk review on local CPU: Gemma 3 4B required **16.66 minutes (999.5s)**; Qwen 2.5 Coder 3B required **10.69 minutes (641.6s)**.
- **Claim-to-Evidence Audit:** Zero unsupported claims; documented model quirks (Gemma return-type contradiction, Qwen prompt leakage) and offline vs telemetry boundaries.

---

## Local Setup & Quickstart

### Prerequisites
- **Python 3.12+** (tested on 3.12.10) with `uv` (tested on 0.12.23)
- **Flutter 3.24+** (tested on Flutter 3.24.5 with Windows desktop toolchain)
- **Ollama** (tested on 0.40.6) running locally with `gemma3:4b` and `qwen2.5-coder:3b`:
  ```bash
  ollama pull gemma3:4b
  ollama pull qwen2.5-coder:3b
  ```

### 1. Install & Verify Python Engine
From the repository root (`w3-close-the-laptop`):
```bash
# Sync dependencies
uv sync

# Run code linters
uv run ruff check src tests
uv run ruff format --check src tests

# Run Python regression suite (168 tests)
uv run pytest -q

# Run M4B boundary matrix (7 scenarios)
uv run python eval/verify_m4_trace_matrix.py
```

### 2. Verify Flutter Desktop Client
From `w3-close-the-laptop/desktop`:
```bash
# Run Dart static analysis (0 errors)
dart analyze .

# Run Flutter desktop test suite (38 tests)
flutter test
```

### 3. Launch SteadyDev (Two-Process Startup)
To run the full graphical desktop application:

1. **Terminal 1 — Start the Python Loopback Engine:**
   ```bash
   uv run python -m steadydev.server --repo-path . --port 8765 --token dev-token-123
   ```
2. **Terminal 2 — Start the Flutter Desktop Client:**
   ```bash
   cd desktop
   flutter run -d windows
   ```

*Note: If the backend is not started first, SteadyDev displays a clear offline warning banner with a working `Retry` button.*

### 4. Sentry Agent Tracing (Optional & Consented)
Telemetry is **100% disabled by default** (`STEADYDEV_SENTRY_ENABLED=0`). To enable Sentry Agent Tracing:
1. Configure your DSN in `.env`:
   ```bash
   STEADYDEV_SENTRY_ENABLED=1
   SENTRY_DSN=https://<your_key>@<org>.ingest.sentry.io/<project>
   ```
2. Or toggle Sentry ON directly inside the desktop app via the **Telemetry Settings** dialog.

---

## Verified Partner Traces & Role Matrix

| Technology | Role in SteadyDev | Verified Trace / Artifact | License / Terms |
| :--- | :--- | :--- | :--- |
| **Sentry Agent Tracing** | Primary contest partner target. 15-span review pipeline tracing, zero code egress, cross-process correlation. | Trace 1: [`694c5b41fb49436caaac6712c9529fc1`](https://o4512305905795072.sentry.io/explore/traces/trace/694c5b41fb49436caaac6712c9529fc1/)<br>Trace 2: [`063830456b804759a92671685dcfa2df`](https://o4512305905795072.sentry.io/explore/traces/trace/063830456b804759a92671685dcfa2df/) | MIT (`sentry-sdk`) |
| **Gemma 3 4B** | Primary default reviewer (`D-11`). Semantic intent evaluation, receipt checking, restart note synthesis on CPU. | Exercised in live multi-chunk run with verified Sentry trace `694c5b41...` | Google Gemma Terms of Use (Open-weight, non-OSI) |
| **Qwen 2.5 Coder 3B** | Fast local CPU fallback (~36% faster than Gemma 3 on CPU). Signature and doc drift evaluation. | Exercised in live multi-chunk run with verified Sentry trace `06383045...` | Apache-2.0 |
| **Thinking Machines Tinker** | Evaluated via conditional cloud LoRA experiment; +0.0 pp delta missed threshold; cut line executed; omitted from submission. | `eval/results/tinker_experiment_results.json` | Proprietary SDK (excluded from release) |
| **Entire** | Skipped due to Antigravity GUI workflow incompatibility (`D-13`, `D-14`). | Documented in `memory/decisions.md` | Omitted from submission |
| **DevRelay** | Private coding-agent session preservation. Not a contest prize track. | Private session `w3-m4b-sentry-...-ymqh8h` | Developer tooling |

---

## Post-Deadline Changes Policy

In strict accordance with Hacktoberfest challenge rules, all code and documentation in this repository were created during the official contest window (October 19–25, 2026). Any commits made after the submission deadline will be explicitly enumerated below with commit SHAs, dates, and rationale.

*No post-deadline commits have been made.*

---

## License

SteadyDev is licensed under the [MIT License](LICENSE).  
Copyright (c) 2026 G00dS0ul-Hackerton.
