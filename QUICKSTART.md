# SteadyDev Quickstart Guide (Windows Preview v0.1.0)

Welcome to **SteadyDev**! SteadyDev is a local-first, open-weight AI companion designed to help developers end their work sessions with clarity.

This guide walks you through setting up and running the Windows preview release.

---

## 1. System Requirements

- **Operating System:** Windows 10 (version 1809+) or Windows 11, 64-bit (x64).
- **CPU / RAM:** Multi-core x86_64 CPU, 8 GB RAM minimum (16 GB recommended for local 4B model inference).
- **Disk Space:** ~150 MB for the SteadyDev release bundle; ~5 GB disk space if installing Ollama models.

---

## 2. Prerequisites

### A. Python & Package Manager (Required for Backend Engine)
SteadyDev uses a lightweight Python 3.12+ loopback engine for Git analysis and model orchestration.
- **Option 1 (Fastest & Recommended):** Install **uv** from [astral.sh/uv](https://docs.astral.sh/uv/):
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- **Option 2:** Install standard **Python 3.12+** from [python.org](https://www.python.org/downloads/) (ensure *"Add python.exe to PATH"* is checked during installation).

### B. Ollama Local LLM Runner (Recommended for Open-Weight Models)
SteadyDev performs local semantic review using open-weight models via Ollama.
1. Download and install **Ollama for Windows** from [ollama.ai](https://ollama.ai).
2. Pull the recommended review models:
   ```bash
   ollama pull gemma3:4b
   ollama pull qwen2.5-coder:3b
   ```
*Note: If Ollama is not installed or running, SteadyDev automatically falls back to its built-in zero-LLM deterministic baseline. You can still use the app offline without Ollama!*

### C. Git for Windows (Required)
SteadyDev analyzes local git diffs and test receipts. Ensure [Git for Windows](https://git-scm.com/) is installed and on your PATH.

---

## 3. Launching SteadyDev

### Quick Launch (Recommended)
1. Extract `steadydev-windows-preview-v0.1.0.zip` to a folder of your choice (e.g. `C:\Tools\SteadyDev`).
2. Double-click **`start-steadydev.bat`**.
   - The launcher will check for `uv` or `python`.
   - It will check if Ollama is running (or notify you of baseline mode).
   - It will start the backend loopback server minimized in the background.
   - It will launch the Flutter desktop application (`desktop\desktop.exe`).

### Manual Launch (Two-Terminal Workflow)
If you prefer running components directly from PowerShell or Command Prompt:

1. **Terminal 1 — Start the Python Loopback Engine:**
   ```bash
   cd backend
   uv sync
   uv run python -m steadydev.server --repo-path . --port 8765 --token dev-token-123
   ```
   *(Or with standard pip: `pip install -e .` then `python -m steadydev.server --repo-path . --port 8765 --token dev-token-123`)*

2. **Terminal 2 — Start the Desktop Client:**
   ```bash
   cd desktop
   .\desktop.exe
   ```

*Note: If the desktop app displays an "Offline Engine" banner on startup, wait 2 seconds for the Python engine to bind its port and click **Retry**.*

---

## 4. How to Use SteadyDev in 5 Minutes

1. **Select Your Project Repository:**
   - In the top header bar, click the repository selector pill (`[ ⑂ sample-project ▾ ]`).
   - Enter or browse to the path of any local Git repository you are actively working on.
2. **Set Session Intention:**
   - Enter your goal for the session (e.g. *"Refactor user authentication and verify unit tests pass"*).
   - Add any specific checklist criteria you plan to complete.
3. **Run a Quiet Review:**
   - Click **"Check changes"**.
   - SteadyDev captures a bounded diff of your modified files and inspects passing test receipts.
   - Gemma 3 (or fallback) reviews your changes and highlights missing check receipts under *"Worth a second look"*.
4. **Inspect the Closing Card:**
   - Switch to the **Closing Card** tab (`Ctrl+Tab` or click the tab).
   - See your work clearly separated into **Changed**, **Checked**, **Uncertain**, and **Deferred**.
   - Review the auto-generated restart note. Edit it with personal reminders for tomorrow.
5. **Leave It Here:**
   - Click **"Leave it here"**.
   - Your session and restart notes are atomically saved to local SQLite (`%LOCALAPPDATA%\SteadyDev\steadydev.db`).
   - Close your laptop with clarity!

---

## 5. Security, Privacy & Telemetry Disclosures

- **100% Local-First Privacy:** All Git diff analysis, file reading, prompt generation, and SQLite storage occur entirely on your local machine (`127.0.0.1`). Your proprietary source code never leaves your device.
- **Opt-In Telemetry (Sentry Agent Tracing):**
  - Telemetry is **100% disabled by default** (`STEADYDEV_SENTRY_ENABLED=0`).
  - If you choose to enable Sentry tracing (by adding `STEADYDEV_SENTRY_ENABLED=1` and a DSN in `.env`), strict privacy scrubbers guarantee that zero code diffs, prompts, or personal file paths are transmitted on the wire. Only pipeline phase durations and operational metrics are sent.
- **Unsigned Preview Binary Notice:**
  - This is an open-source preview build for the Hacktoberfest 2026 challenge. The executable `desktop.exe` is unsigned.
  - Windows SmartScreen may show an *"Unknown Publisher"* prompt. Click **"More info"** and **"Run anyway"**.
  - You can verify the integrity of the downloaded archive using the provided SHA-256 checksum:
    ```powershell
    Get-FileHash steadydev-windows-preview-v0.1.0.zip -Algorithm SHA256
    ```
- **Advisory AI Notice:**
  - Finding suggestions and restart notes generated by local language models are advisory assistance and do not constitute formal code certification or proof of correctness.

---

## 6. Troubleshooting

- **"Engine is Offline" Warning:**  
  Click the **Retry** button in the top banner. If it does not connect, verify that Terminal 1 / `start-steadydev.bat` is running and that port `8765` is not occupied by another application.
- **Model Inference is Slow on CPU:**  
  Running a 4B parameter model (`gemma3:4b`) on CPU can take 2–3 minutes per diff chunk. For faster reviews, SteadyDev will automatically offer Qwen 2.5 Coder 3B or the instantaneous deterministic baseline.
- **Process Cleanup:**  
  Closing the Flutter desktop window cleanly triggers the Python backend watchdog thread to shut down the server process automatically within 1 second.
