import subprocess
from pathlib import Path
import pytest

def test_launcher_batch_syntax():
    """Verify start-steadydev.bat parses without CMD syntax errors."""
    bat_path = Path(__file__).resolve().parent.parent / "start-steadydev.bat"
    assert bat_path.exists(), f"Batch launcher not found at {bat_path}"

    # Run cmd.exe /c against the batch script
    # We pass a non-existent repo or dry run to avoid actually starting processes
    res = subprocess.run(
        ["cmd.exe", "/c", str(bat_path), "--test-syntax"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    # The batch parser must not fail with CMD syntax errors (e.g. 'unexpected at this time')
    assert "unexpected at this time" not in res.stderr.lower(), f"Batch syntax error detected: {res.stderr}"
    assert "unexpected at this time" not in res.stdout.lower(), f"Batch syntax error detected in stdout: {res.stdout}"
