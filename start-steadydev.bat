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
        echo Please install uv - see https://docs.astral.sh/uv/ - or Python 3.12+.
        echo See QUICKSTART.md for setup instructions.
        echo.
        pause
        exit /b 1
    )
)

REM 2. Check for Git
where git >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] 'git' was not found on your PATH. Git is required to track code changes.
    echo Please install Git for Windows: https://git-scm.com/
    echo.
    pause
    exit /b 1
) else (
    echo [OK] Detected 'git'.
)

REM 3. Advisory check for Ollama daemon
curl.exe --connect-timeout 2 --max-time 3 -s http://127.0.0.1:11434/api/tags >nul 2>nul
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

REM 4. Resolve directory paths using 8.3 short paths (resolves Unicode/emoji paths)
set ROOT_DIR=%~dps0
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
        echo.
        pause
        exit /b 1
    )
)

REM Handle syntax check / test flag
if "%~1"=="--test-syntax" (
    echo [OK] Syntax check passed.
    exit /b 0
)

REM 5. Resolve Target Git Repository
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

REM 6. Start Python loopback backend engine
echo Starting SteadyDev Python engine on 127.0.0.1:8765...
cd /d "%BACKEND_DIR%"
start "SteadyDev Backend Engine" /min %RUN_CMD% --repo-path "!TARGET_REPO!" --port 8765 --token dev-token-123

REM 7. Wait for backend server to be healthy
echo Waiting for SteadyDev backend engine to initialize...
set BACKEND_READY=0
for /L %%i in (1,1,20) do (
    if !BACKEND_READY! EQU 0 (
        curl.exe --connect-timeout 1 --max-time 2 -s http://127.0.0.1:8765/api/health >nul 2>nul
        if !ERRORLEVEL% EQU 0 (
            set BACKEND_READY=1
            echo [OK] Backend engine is ready.
        ) else (
            ping 127.0.0.1 -n 2 >nul
        )
    )
)

if !BACKEND_READY! EQU 0 (
    echo [WARNING] Backend engine did not respond on port 8765 within 20s.
    echo Launching desktop client anyway; you can click 'Retry' once the engine starts.
)

REM 8. Launch Flutter Desktop Client
echo Launching SteadyDev Desktop Client...
start "" "%DESKTOP_EXE%"

echo.
echo ====================================================================
echo   SteadyDev is now running!
echo   If the desktop window displays an offline banner on launch, click 'Retry'.
echo   Press any key to close this launcher window (or keep it open for logs).
echo ====================================================================
echo.
pause
