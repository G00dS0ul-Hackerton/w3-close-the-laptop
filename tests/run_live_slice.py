"""Live end-to-end vertical slice script for SteadyDev Milestone M2.

Connects loopback server on 127.0.0.1:0, queries /api/health, /api/snapshot,
and executes real inference against Ollama qwen2.5-coder:3b.
"""

import pathlib
import subprocess
import sys
import threading
import time

import httpx

from steadydev.ollama_client import OllamaClient
from steadydev.reviewer import Reviewer
from steadydev.server import create_server


def _ensure_fixture_repo(repo_path: pathlib.Path) -> None:
    """Ensure sample_repo is an initialized git repository for live tests."""
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "TestDev"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        # Commit base files
        subprocess.run(
            ["git", "add", "src/index.ts"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        if (repo_path / "src" / "auth" / "redirect.ts").exists():
            subprocess.run(
                ["git", "add", "src/auth/redirect.ts"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )


def main() -> int:
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr.encoding.lower() != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8")

    repo_path = pathlib.Path("tests/fixtures/sample_repo").resolve()
    _ensure_fixture_repo(repo_path)
    token = "test-secret-token-1234567890abcdef"

    print(f"1. Target repo: {repo_path}")
    client = OllamaClient(base_url="http://127.0.0.1:11434")
    reviewer = Reviewer(ollama_client=client)

    server = create_server(
        repo_root=repo_path,
        port=0,
        token=token,
        ollama_client=client,
        reviewer=reviewer,
    )
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"
    headers = {"Authorization": f"Bearer {token}"}

    print(f"2. Loopback server bound to: {base_url}")

    try:
        # Step 1: Health check
        t0 = time.perf_counter()
        resp = httpx.get(f"{base_url}/api/health", headers=headers, timeout=10.0)
        assert resp.status_code == 200, f"Health failed: {resp.text}"
        health_data = resp.json()
        print(
            f"   -> /api/health OK ({time.perf_counter() - t0:.3f}s): active_model={health_data['active_model']}, model_status={health_data['model_status']}"
        )

        # Step 2: Snapshot check
        t1 = time.perf_counter()
        resp = httpx.post(
            f"{base_url}/api/snapshot",
            headers=headers,
            json={"repo_path": str(repo_path)},
            timeout=10.0,
        )
        assert resp.status_code == 200, f"Snapshot failed: {resp.text}"
        snap_data = resp.json()
        changed_paths = [f["path"] for f in snap_data["changed_files"]]
        print(
            f"   -> /api/snapshot OK ({time.perf_counter() - t1:.3f}s): {len(snap_data['changed_files'])} changed files: {changed_paths}"
        )

        # Step 3: Real Ollama Review Check
        print("3. Executing real Ollama review query against qwen2.5-coder:3b...")
        review_payload = {
            "repo_path": str(repo_path),
            "session_intention": "Fix the login redirect and make the dashboard work on mobile.",
            "acceptance_criteria": [
                "Login redirect validates open redirect and keeps user on origin",
                "Mobile dashboard layout applies column styling under 600px",
            ],
            "check_receipts": [
                {
                    "receipt_id": "receipt-001",
                    "command": "npm test test/redirect.test.ts",
                    "exit_code": 0,
                    "output_summary": "4 passed in 0.12s. Redirect assertions passed.",
                    "timestamp_utc": "2026-10-21T10:00:00Z",
                }
            ],
            "prior_findings": [],
            "explicit_deferrals": [],
        }

        t2 = time.perf_counter()
        resp = httpx.post(
            f"{base_url}/api/review",
            headers=headers,
            json=review_payload,
            timeout=180.0,
        )
        elapsed = time.perf_counter() - t2
        assert resp.status_code == 200, f"Review failed: {resp.status_code} {resp.text}"
        review_data = resp.json()

        print(
            f"   -> /api/review OK ({elapsed:.2f}s)! Returned {len(review_data['findings'])} findings:"
        )
        for idx, f in enumerate(review_data["findings"], 1):
            category = f.get("category", "finding").upper()
            description = f.get("description", "")
            locator = f.get("locator", "")
            evidence = f.get("evidence", "")
            print(f"      Finding {idx}: [{category}] at {locator}")
            print(f"        Description: {description}")
            print(f"        Evidence: {evidence[:100]}...")

        print("\n4. Feasibility gate criteria verified successfully.")
        return 0
    finally:
        server.shutdown()
        print("5. Server shut down cleanly.")


if __name__ == "__main__":
    sys.exit(main())
