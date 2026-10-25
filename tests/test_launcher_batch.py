import subprocess
from pathlib import Path


def test_launcher_batch_syntax():
    """Verify start-steadydev.bat parses without CMD syntax errors."""
    bat_path = Path(__file__).resolve().parent.parent / "start-steadydev.bat"
    assert bat_path.exists(), f"Batch launcher not found at {bat_path}"

    # Run cmd.exe /c against the batch script
    # We pass a non-existent repo or dry run to avoid actually starting processes
    res = subprocess.run(
        ["cmd.exe", "/c", str(bat_path), "--test-syntax"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    # The batch parser must not fail with CMD syntax errors (e.g. 'unexpected at this time')
    assert "unexpected at this time" not in res.stderr.lower(), f"Batch syntax error detected: {res.stderr}"
    assert "unexpected at this time" not in res.stdout.lower(), f"Batch syntax error detected in stdout: {res.stdout}"


def test_launcher_no_syntax_typos():
    """Regression test: start-steadydev.bat must not contain malformed !ERRORLEVEL% typo."""
    bat_path = Path(__file__).resolve().parent.parent / "start-steadydev.bat"
    content = bat_path.read_text(encoding="utf-8")
    assert "!ERRORLEVEL%" not in content, (
        "Found malformed variable syntax '!ERRORLEVEL%' in start-steadydev.bat (should be !ERRORLEVEL!)"
    )
    assert "!ERRORLEVEL! EQU 0" in content, (
        "Expected delayed-expansion check '!ERRORLEVEL! EQU 0' in start-steadydev.bat"
    )


def test_launcher_readiness_failure(tmp_path):
    """Regression test: if backend readiness check fails, the launcher must NOT
    announce that SteadyDev is running, must NOT launch the desktop client,
    and must exit with code 1.
    """
    bat_path = Path(__file__).resolve().parent.parent / "start-steadydev.bat"
    content = bat_path.read_text(encoding="utf-8")

    # Static assertion: script must contain clean error handling and not fall through
    assert "[ERROR] SteadyDev backend engine failed to respond on port 8765 within 20s." in content, (
        "Missing backend engine failure message in start-steadydev.bat"
    )
    assert "SteadyDev desktop client was not launched." in content, (
        "Missing notice that desktop client was not launched in start-steadydev.bat"
    )

    # Dynamic execution: execute the readiness decision block in CMD with BACKEND_READY=0
    readiness_idx = content.rfind("if !BACKEND_READY! EQU 0")
    assert readiness_idx != -1, "Could not locate readiness check in start-steadydev.bat"

    snippet = content[readiness_idx:]
    test_bat = tmp_path / "test_readiness.bat"
    test_bat.write_text(
        f"@echo off\nsetlocal EnableDelayedExpansion\nset BACKEND_READY=0\nset DESKTOP_EXE=mock_desktop.exe\n{snippet}\n",
        encoding="utf-8",
    )

    res = subprocess.run(
        ["cmd.exe", "/c", str(test_bat)],
        input="\n",
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert res.returncode == 1, f"Expected returncode 1 on readiness failure, got {res.returncode}"
    assert "SteadyDev is now running!" not in res.stdout, (
        f"Contradictory announcement 'SteadyDev is now running!' was output on readiness failure:\n{res.stdout}"
    )
    assert "SteadyDev desktop client was not launched." in res.stdout, (
        f"Expected 'SteadyDev desktop client was not launched.' in stdout:\n{res.stdout}"
    )


def test_create_shortcut_script_interactive_decline(tmp_path):
    """create-shortcut.ps1 must prompt for user confirmation and exit without creating shortcut if declined."""
    ps1_path = Path(__file__).resolve().parent.parent / "create-shortcut.ps1"
    assert ps1_path.exists(), f"create-shortcut.ps1 not found at {ps1_path}"

    res = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps1_path),
            "-DestinationDir",
            str(tmp_path),
        ],
        input="n\n",
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert res.returncode == 0, f"Expected 0 on decline, got {res.returncode}"
    assert "Shortcut creation cancelled" in res.stdout
    assert not (tmp_path / "SteadyDev.lnk").exists()


def test_create_shortcut_script_forced(tmp_path):
    """create-shortcut.ps1 with -Force must create valid SteadyDev.lnk pointing to desktop.exe."""
    ps1_path = Path(__file__).resolve().parent.parent / "create-shortcut.ps1"
    assert ps1_path.exists(), f"create-shortcut.ps1 not found at {ps1_path}"

    res = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps1_path),
            "-Force",
            "-DestinationDir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert res.returncode == 0, f"Failed to create shortcut: {res.stderr}\nSTDOUT:\n{res.stdout}"
    assert "[OK] SteadyDev shortcut created successfully" in res.stdout
    lnk_file = tmp_path / "SteadyDev.lnk"
    assert lnk_file.exists()
    assert lnk_file.stat().st_size > 0
