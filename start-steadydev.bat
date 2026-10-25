@echo off
setlocal EnableDelayedExpansion
title SteadyDev Launcher (Preview v0.1.0)

echo ====================================================================
echo   SteadyDev - Close Your Laptop with Clarity (Preview v0.1.0)
echo   Local-First Open-Weight Code Reviewer
echo ====================================================================
echo.

REM 1. Check for uv or Python
where uv >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set RUN_CMD=uv run python -m steadydev.server
    echo [OK] Detected 'uv' package manager.
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        set RUN_CMD=python -m steadydev.server
        echo [OK] Detected 'python'.
    ) else (
        echo [ERROR] Neither 'uv' nor 'python' was found on your PATH.
        echo Please install uv (recommended: https://docs.astral.sh/uv/) or Python 3.12+.
        echo See QUICKSTART.md for setup instructions.
        echo.
        pause
        exit /b 1
    )
)

REM 2. Advisory check for Ollama daemon
curl -s http://127.0.0.1:11434/api/tags >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [NOTICE] Local Ollama daemon not detected at http://127.0.0.1:11434.
    echo SteadyDev will start in offline deterministic baseline mode.
    echo To enable local Gemma 3 or Qwen review, run Ollama and execute:
    echo   ollama pull gemma3:4b
    echo   ollama pull qwen2.5-coder:3b
    echo.
) else (
    echo [OK] Detected active local Ollama daemon.
)

REM 3. Resolve directory paths
set ROOT_DIR=%~dp0
if exist "%ROOT_DIR%backend" (
    set BACKEND_DIR=%ROOT_DIR%backend
) else (
    set BACKEND_DIR=%ROOT_DIR%
)

if exist "%ROOT_DIR%desktop\desktop.exe" (
    set DESKTOP_EXE=%ROOT_DIR%desktop\desktop.exe
) else (
    if exist "%ROOT_DIR%desktop\build\windows\x64\runner\Release\desktop.exe" (
        set DESKTOP_EXE=%ROOT_DIR%desktop\build\windows\x64\runner\Release\desktop.exe
    ) else (
        echo [ERROR] Could not locate desktop.exe.
        echo Expected at %ROOT_DIR%desktop\desktop.exe.
        pause
        exit /b 1
    )
)

REM 4. Resolve Target Git Repository
if not "%~1"=="" (
    set TARGET_REPO=%~1
) else (
    if exist "%CD%\.git" (
        set TARGET_REPO=%CD%
    ) else (
        if exist "%ROOT_DIR%sample-project\.git" (
            set TARGET_REPO=%ROOT_DIR%sample-project
        ) else (
            echo Initializing starter sample repository at %ROOT_DIR%sample-project...
            if not exist "%ROOT_DIR%sample-project" mkdir "%ROOT_DIR%sample-project"
            pushd "%ROOT_DIR%sample-project"
            git init -q
            git config user.name "SteadyDev User"
            git config user.email "user@steadydev.local"
            if not exist README.md (
                echo # Sample Project for SteadyDev Review > README.md
                echo This is a sample project to explore SteadyDev. >> README.md
                git add README.md
                git commit -q -m "Initial commit"
            )
            popd
            set TARGET_REPO=%ROOT_DIR%sample-project
        )
    )
)

echo [OK] Target Git Repository: !TARGET_REPO!

REM 5. Start Python loopback backend engine
echo Starting SteadyDev Python engine on 127.0.0.1:8765...
cd /d "%BACKEND_DIR%"
start "SteadyDev Backend Engine" /min %RUN_CMD% --repo-path "!TARGET_REPO!" --port 8765 --token dev-token-123

REM Give backend server 2 seconds to initialize socket
timeout /t 2 /nobreak >nul

REM 6. Launch Flutter Desktop Client
echo Launching SteadyDev Desktop Client...
start "" "%DESKTOP_EXE%"

echo.
echo SteadyDev is now running!
echo If the desktop window displays an offline banner on launch, click 'Retry'.
echo Closing the desktop application will automatically terminate the backend engine.
echo.
timeout /t 4 >nul
exit /b 0
