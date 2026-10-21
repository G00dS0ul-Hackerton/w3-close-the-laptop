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

## Current Milestone: M1 — Real Local Reviewer Feasibility

Milestone M1 establishes the feasibility of local open-weight code reviewing on CPU using Ollama before presentation UI work.

### Key Capabilities in M1
- **Deterministic Checklist Baseline:** A zero-LLM reference engine (<5 ms) that verifies criteria, check receipts, and deferral markers.
- **Local Open-Weight Inference:** Sequential comparative evaluation of `gemma3:4b` and `qwen2.5-coder:3b` on identical frozen test packets.
- **Bounded Packet Security:** Strict allowlisting, diff truncation (max 400 lines / 8 KB), XML delimiter data-inertia framing against prompt injection, and multi-variant Windows path/username redaction.
- **Deterministic Locator Validation:** 4-step post-processing guard preventing locator forgery and directory traversal.
- **Graceful Error Handling:** Safe degradation on Ollama outages or malformed outputs without crashing.

---

## Local Setup

### Prerequisites
- Python 3.12+ (tested on Python 3.12.10)
- `uv` package manager (tested on uv 0.12.23)
- Ollama (tested on Ollama 0.40.6) with candidate models:
  ```bash
  ollama pull gemma3:4b
  ollama pull qwen2.5-coder:3b
  ```

### Installation
From the repository root (`w3-close-the-laptop`):
```bash
uv sync
```

### Running Tests
```bash
uv run ruff check
uv run ruff format --check
uv run pytest -q
```

### Running the Evaluation Benchmark
```bash
uv run python eval/run_eval.py
```
