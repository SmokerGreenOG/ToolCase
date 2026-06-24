@echo off
REM =====================================================================
REM  install_toolcase.bat — ToolCase v5.4.1 Windows Installer
REM  pip install, compile check, test run, release readiness.
REM  HARD FAIL on every check — no warnings tolerated.
REM  Maker: SmokerGreenOG
REM =====================================================================
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║      ToolCase v5.4.1 — Windows Installer                   ║
echo ║      62 tools · 10 safety rules · RSI v2.0 · safe_run      ║
echo ║      Maker: SmokerGreenOG                                  ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM ── Detect ToolCase directory (the directory containing this script) ──
set "TC_DIR=%~dp0"
if "%TC_DIR%"=="" set "TC_DIR=%CD%"
echo 📍 ToolCase directory: %TC_DIR%
pushd "%TC_DIR%"

REM ── 1. Python version check (3.11+) ──────────────────────────
echo.
echo [1/7] Checking Python ≥ 3.11...
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ Python not found. Install Python 3.11+ from https://www.python.org/
    popd && pause && exit /b 1
)

python -c "import sys; v=sys.version_info; assert v >= (3,11), f'Need 3.11+, have {v.major}.{v.minor}'; print(f'✅ Python {v.major}.{v.minor}.{v.micro}')"
if %ERRORLEVEL% neq 0 (
    echo ❌ Python 3.11+ required. Current version is too old.
    popd && pause && exit /b 1
)

REM ── 2. pip install . ─────────────────────────────────────────
echo.
echo [2/7] Installing ToolCase via pip...
python -m pip install . --quiet
if %ERRORLEVEL% neq 0 (
    echo ❌ pip install failed.
    popd && pause && exit /b 1
)
echo ✅ pip install succeeded

REM ── 3. Compile check ALL Python files ─────────────────────────
echo.
echo [3/7] Compile-checking all Python files...
set ERRORS=0
for /r "%TC_DIR%" %%f in (*.py) do (
    echo %%~f | findstr /C:"__pycache__" >nul && goto :skip_compile
    echo %%~f | findstr /C:".rsi_" >nul && goto :skip_compile
    echo %%~f | findstr /C:".venv" >nul && goto :skip_compile
    python -m py_compile "%%f" >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo    ❌ %%~nxf — COMPILE ERROR
        set /a ERRORS+=1
    )
    :skip_compile
)

if !ERRORS! gtr 0 (
    echo ❌ !ERRORS! file(s) have compile errors.
    popd && pause && exit /b 1
)
echo ✅ All Python files compile successfully

REM ── 4. Run tests ──────────────────────────────────────────────
echo.
echo [4/7] Running tests...
python -m pytest tests -q --tb=short
if %ERRORLEVEL% neq 0 (
    echo ❌ Tests failed.
    popd && pause && exit /b 1
)
echo ✅ All tests passed

REM ── 5. Verify install ─────────────────────────────────────────
echo.
echo [5/7] Verifying installation...
python improve.py --verify-install
if %ERRORLEVEL% neq 0 (
    echo ❌ verify-install failed.
    popd && pause && exit /b 1
)

REM ── 6. Release readiness ─────────────────────────────────────
echo.
echo [6/7] Checking release readiness...
python release_readiness.py --ci
if %ERRORLEVEL% neq 0 (
    echo ❌ Release readiness check failed.
    popd && pause && exit /b 1
)
echo ✅ Release readiness: GO

REM ── 7. Hermes skill installation (optional) ──────────────────
echo.
echo [7/7] Installing Hermes skill...
if exist "%USERPROFILE%\.hermes\skills\" (
    echo    Hermes skills directory found
    set "SKILL_DIR=%USERPROFILE%\.hermes\skills\toolcase-self-improve"
    if not exist "!SKILL_DIR!" mkdir "!SKILL_DIR!"

    REM Copy skill files: SKILL.md, manifest.json, AND scripts
    copy /Y "%TC_DIR%SKILL.md" "!SKILL_DIR!\SKILL.md" >nul
    if %ERRORLEVEL% neq 0 (
        echo ❌ Failed to copy SKILL.md
        popd && pause && exit /b 1
    )
    copy /Y "%TC_DIR%manifest.json" "!SKILL_DIR!\manifest.json" >nul
    if %ERRORLEVEL% neq 0 (
        echo ❌ Failed to copy manifest.json
        popd && pause && exit /b 1
    )

    REM Copy scripts referenced by manifest.json
    if not exist "!SKILL_DIR!\scripts" mkdir "!SKILL_DIR!\scripts"
    xcopy /Y /Q "%TC_DIR%scripts\*.py" "!SKILL_DIR!\scripts\" >nul
    if not exist "!SKILL_DIR!\references" mkdir "!SKILL_DIR!\references"
    xcopy /Y /Q "%TC_DIR%references\*.md" "!SKILL_DIR!\references\" >nul 2>nul

    echo ✅ ToolCase skill installed for Hermes
    echo    Use: hermes -s toolcase-self-improve
) else (
    echo    ⚠ Hermes skills directory not found — skipping skill install
    echo    Install Hermes Agent from https://hermes-agent.nousresearch.com
    echo    Then re-run this script or manually copy SKILL.md to ~/.hermes/skills/toolcase-self-improve/
)

REM ── Summary ──────────────────────────────────────────────────
echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║      ✅ ToolCase v5.4.1 — Installation Complete             ║
echo ╠══════════════════════════════════════════════════════════════╣
echo ║  📍 %TC_DIR%
echo ║  🛠  62 tools · 10 safety rules · RSI v2.0
echo ║  🔒 safe_run executor · workspace containment
echo ║  🌐  EN/NL/DE i18n
echo ║                                                              ║
echo ║  Quick start:                                                ║
echo ║    python improve.py --list-tools          (show 62 tools)   ║
echo ║    python improve.py --core-scan .         (10 read-only)    ║
echo ║    python self_improve_loop.py . --dry-run (dry run)         ║
echo ║    python release_readiness.py             (pre-release)     ║
echo ║                                                              ║
echo ║  CLI entry point (after pip install):                        ║
echo ║    toolcase --version                                        ║
echo ║    toolcase --list-tools                                     ║
echo ║    toolcase --verify-install                                 ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

popd
pause
exit /b 0
