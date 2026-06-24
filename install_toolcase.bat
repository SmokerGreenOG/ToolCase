@echo off
REM =====================================================================
REM  install_toolcase.bat — ToolCase v5.4.2 Windows Installer
REM  pip install, compile check, test run, release readiness.
REM  HARD FAIL on every check — no warnings tolerated.
REM  Maker: SmokerGreenOG
REM =====================================================================
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║      ToolCase v5.4.2 — Windows Installer                   ║
echo ║      62 tools · 10 safety rules · RSI v2.0 · safe_run      ║
echo ║      Maker: SmokerGreenOG                                  ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM ── Detect ToolCase directory ──
set "TC_DIR=%~dp0"
if "%TC_DIR%"=="" set "TC_DIR=%CD%"
echo 📍 ToolCase directory: %TC_DIR%
pushd "%TC_DIR%"

REM ── 1. Python ≥ 3.11 check ────────────────────────────────────
echo.
echo [1/8] Checking Python ≥ 3.11...
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ Python not found. Install Python 3.11+ from https://www.python.org/
    popd && pause && exit /b 1
)
python -c "import sys; v=sys.version_info; assert v>=(3,11),f'Need 3.11+, have {v.major}.{v.minor}'; print(f'✅ Python {v.major}.{v.minor}.{v.micro}')"
if %ERRORLEVEL% neq 0 (
    echo ❌ Python 3.11+ required.
    popd && pause && exit /b 1
)

REM ── 2. pip install .[test] ────────────────────────────────────
echo.
echo [2/8] Installing ToolCase + test dependencies...
python -m pip install ".[test]" --quiet
if %ERRORLEVEL% neq 0 (
    echo ❌ pip install failed.
    popd && pause && exit /b 1
)
echo ✅ pip install succeeded

REM ── 3. Test installed CLI (not source) ─────────────────────────
echo.
echo [3/8] Testing installed CLI...
toolcase --version
if %ERRORLEVEL% neq 0 (
    echo ❌ toolcase --version failed
    popd && pause && exit /b 1
)
toolcase --list-tools >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ toolcase --list-tools failed
    popd && pause && exit /b 1
)
toolcase --verify-install
if %ERRORLEVEL% neq 0 (
    echo ❌ toolcase --verify-install failed
    popd && pause && exit /b 1
)
python -m pip check
if %ERRORLEVEL% neq 0 (
    echo ❌ pip check failed
    popd && pause && exit /b 1
)
echo ✅ Installed CLI verified

REM ── 4. Compile check ALL Python files (no goto — nested if) ───
echo.
echo [4/8] Compile-checking all Python files...
set ERRORS=0
for /r "%TC_DIR%" %%f in (*.py) do (
    echo %%~f | findstr /C:"__pycache__" >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo %%~f | findstr /C:".rsi_" >nul 2>&1
        if !ERRORLEVEL! neq 0 (
            echo %%~f | findstr /C:".venv" >nul 2>&1
            if !ERRORLEVEL! neq 0 (
                echo %%~f | findstr /C:"\build\" >nul 2>&1
                if !ERRORLEVEL! neq 0 (
                    echo %%~f | findstr /C:"\dist\" >nul 2>&1
                    if !ERRORLEVEL! neq 0 (
                        python -m py_compile "%%f" >nul 2>&1
                        if !ERRORLEVEL! neq 0 (
                            echo    ❌ %%~nxf — COMPILE ERROR
                            set /a ERRORS+=1
                        )
                    )
                )
            )
        )
    )
)

if !ERRORS! gtr 0 (
    echo ❌ !ERRORS! file(s) have compile errors.
    popd && pause && exit /b 1
)
echo ✅ All Python files compile successfully

REM ── 5. Run tests ──────────────────────────────────────────────
echo.
echo [5/8] Running tests...
python -m pytest tests -q --tb=short
if %ERRORLEVEL% neq 0 (
    echo ❌ Tests failed.
    popd && pause && exit /b 1
)
echo ✅ All tests passed

REM ── 6. Release readiness ─────────────────────────────────────
echo.
echo [6/8] Checking release readiness...
python release_readiness.py --ci
if %ERRORLEVEL% neq 0 (
    echo ❌ Release readiness check failed.
    popd && pause && exit /b 1
)
echo ✅ Release readiness: GO

REM ── 7. Security scan ─────────────────────────────────────────
echo.
echo [7/8] Running security scan...
python security_scan.py . --json >nul 2>&1
if %ERRORLEVEL% gtr 1 (
    echo ❌ Security scan found HIGH/MEDIUM issues.
    popd && pause && exit /b 1
)
echo ✅ Security scan clean

REM ── 8. Hermes skill installation (optional) ──────────────────
echo.
echo [8/8] Installing Hermes skill...
if exist "%USERPROFILE%\.hermes\skills\" (
    echo    Hermes skills directory found
    set "SKILL_DIR=%USERPROFILE%\.hermes\skills\toolcase-self-improve"
    if not exist "!SKILL_DIR!" mkdir "!SKILL_DIR!"

    copy /Y "%TC_DIR%SKILL.md" "!SKILL_DIR!\SKILL.md" >nul || (
        echo ❌ Failed to copy SKILL.md
        popd && pause && exit /b 1
    )
    copy /Y "%TC_DIR%manifest.json" "!SKILL_DIR!\manifest.json" >nul || (
        echo ❌ Failed to copy manifest.json
        popd && pause && exit /b 1
    )

    REM Copy root Python scripts (improve.py, self_improve_loop.py, etc.)
    for %%s in (improve.py self_improve_loop.py security_scan.py project_doctor.py multiscan.py complexity.py depgraph.py dead_code_finder.py todo_tracker.py dependency_audit.py license_checker.py env_check.py safe_run.py command_guard.py) do (
        if exist "%TC_DIR%%%s" (
            copy /Y "%TC_DIR%%%s" "!SKILL_DIR!\%%s" >nul
        )
    )

    REM Copy scripts/ and references/
    if not exist "!SKILL_DIR!\scripts" mkdir "!SKILL_DIR!\scripts"
    xcopy /Y /Q "%TC_DIR%scripts\*.py" "!SKILL_DIR!\scripts\" >nul 2>&1
    if not exist "!SKILL_DIR!\references" mkdir "!SKILL_DIR!\references"
    xcopy /Y /Q "%TC_DIR%references\*.md" "!SKILL_DIR!\references\" >nul 2>&1

    echo ✅ ToolCase skill installed for Hermes
    echo    Use: hermes -s toolcase-self-improve
) else (
    echo    ⚠ Hermes skills directory not found — skipping skill install
)

REM ── Summary ──────────────────────────────────────────────────
echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║      ✅ ToolCase v5.4.2 — Installation Complete             ║
echo ╠══════════════════════════════════════════════════════════════╣
echo ║  📍 %TC_DIR%
echo ║  🛠  62 tools · 10 safety rules · RSI v2.0
echo ║  🔒 safe_run executor · workspace containment
echo ║  🌐  EN/NL/DE i18n
echo ║                                                              ║
echo ║  Quick start:                                                ║
echo ║    toolcase --version                                        ║
echo ║    toolcase --list-tools                                     ║
echo ║    toolcase --core-scan .                                    ║
echo ║    python self_improve_loop.py . --dry-run                   ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

popd
pause
exit /b 0
