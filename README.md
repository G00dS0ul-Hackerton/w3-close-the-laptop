# SteadyDev (Close the Laptop)

> **"You don't have to finish everything today. You just need to know where you stand and how to continue tomorrow."**

SteadyDev is a local-first, open-weight AI companion designed to help developers end their work sessions with clarity. Rather than pressuring you to clear an endless backlog, SteadyDev quietly compares your session goals, code changes, and verification checks. It highlights potential gaps with supporting evidence and generates an editable closing summary with a durable restart note for tomorrow.

Built for the **Hacktoberfest Open-Source AI Challenge 2026 (Week 3: Slow and Steady)**.
- **Repository:** https://github.com/G00dS0ul-Hackerton/w3-close-the-laptop

---

## Core Philosophy

SteadyDev maintains a strict four-way separation of session state:
- **Changed:** What files and functions were modified during the session.
- **Checked:** What tests, typechecks, or viewports were explicitly verified with receipts.
- **Uncertain / Needs Judgment:** What remains unverified (not proof of a defect, but an unrecorded check).
- **Deferred:** What you deliberately set aside for the next session.

---

## Architecture & Milestones

### Milestone M1 — Real Local Reviewer Feasibility (Completed)
Milestone M1 established the feasibility of local open-weight code reviewing on CPU using Ollama before presentation UI work.
- **Deterministic Baseline:** Zero-LLM reference engine (<5 ms) verifying criteria, receipts, and deferral markers.
- **Sequential Model Evaluation:** Evaluated `gemma3:4b` vs `qwen2.5-coder:3b` across 8 canonical test fixtures.
- **Bounded Packet Security:** Strict allowlisting, diff truncation (max 400 lines / 8 KB), and XML delimiter data-inertia framing against prompt injection.
- **Deterministic Locator Validation:** 4-step post-processing guard preventing locator forgery and directory traversal.
- **Graceful Error Handling:** Safe degradation on Ollama outages or malformed outputs without crashing.

---

### Milestone M2 — Real Flutter Vertical Slice & Loopback Engine (Completed)
Milestone M2 connects the native Flutter Windows desktop application to the local Python review engine over an authenticated loopback IPC boundary (`127.0.0.1:0`), executing real inference on CPU against Ollama (`qwen2.5-coder:3b`).

#### Key Capabilities in M2
- **Native Flutter Desktop Client (`desktop/`):**
  - **Modular Architecture:** Ultra-thin `main.dart` (14 lines) and `app.dart` (37 lines) with the desktop shell extracted into `lib/widgets/steady_dev_scaffold.dart`.
  - **Green Brand System:** Implements the visual contract from `prototype.html` in Light (`#f5f8f4`) and Dark (`#001a06`) themes with verified WCAG AA contrast (>4.5:1 text, >3:1 controls).
  - **Three Core Views:**
    - **Session View:** Live session intention card, criteria checklist, and review findings cards.
    - **Quiet Audit View:** Distraction-free audit list filtered by finding lifecycle states (Open, Deferred, Resolved, Dismissed).
    - **Closing View:** Session wrap-up card featuring the non-deferrable restart note editor and closing lock.
  - **Modal Interactions:** Evidence inspection with file locators, Reason capture (Resolve/Defer/Dismiss with context), and Intention editing.
  - **Local Theme Persistence:** Local JSON preference storage in `%LOCALAPPDATA%\SteadyDev\preferences.json`.
- **Python Loopback IPC Server (`src/steadydev/server.py`):**
  - Standard library `ThreadingHTTPServer` bound to ephemeral loopback (`127.0.0.1:0`).
  - Per-launch 256-bit token authentication (`Authorization: Bearer <token>`).
  - Stdin EOF watchdog thread ensuring zero-zombie child process termination when the desktop window closes.
- **Safe Git Snapshot Collector (`src/steadydev/git_collector.py`):**
  - Live Git diff collector enforcing repository boundaries and rejecting directory traversal (`..`).
  - Multi-variant privacy redaction: automatically scrubs Windows paths, usernames, emojis, and sensitive tokens.
- **Deterministic Evidence Guard:**
  - Evaluates user claims and check receipts before LLM inference; enforces that unverified claims are marked `NEEDS_JUDGMENT` with clear limitations rather than hallucinated defects.

---

## Local Setup & Quickstart

### Prerequisites
- **Python 3.12+** (tested on 3.12.10) with `uv` (tested on 0.12.23)
- **Flutter 3.24+** (tested on Flutter 3.24.5 with Windows desktop toolchain)
- **Ollama** (tested on 0.40.6) running locally with `qwen2.5-coder:3b`:
  ```bash
  ollama pull qwen2.5-coder:3b
  ```

### 1. Python Review Engine Setup
From the repository root (`w3-close-the-laptop`):
```bash
# Sync dependencies
uv sync

# Run test suite (63 unit tests)
uv run pytest -q

# Run code linters
uv run ruff check
uv run ruff format --check
```

### 2. Flutter Desktop Application
From `w3-close-the-laptop/desktop`:
```bash
# Run Flutter tests (contrast tokens, responsive layouts, navigation)
flutter test

# Launch Flutter Windows desktop app
flutter run -d windows
```

### 3. Run Live Vertical Slice Verification
To verify the end-to-end integration slice against your local Ollama daemon without launching the full UI:
```bash
uv run python tests/run_live_slice.py
```
This script launches an ephemeral authenticated loopback server, collects the Git snapshot from `tests/fixtures/sample_repo`, and runs real inference through Ollama `qwen2.5-coder:3b`.

---

## Roadmap
- [x] **M1:** Real Local Reviewer Feasibility (Deterministic baseline + Ollama evaluation)
- [x] **M2:** Real Flutter Vertical Slice & Loopback Engine (Flutter desktop app + authenticated loopback IPC)
- [ ] **M3:** Durable Closing Card & Export (Local SQLite persistence, markdown restart note export)
- [ ] **M4:** Final Polish & Open Source Submission
