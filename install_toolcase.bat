@echo off
REM =====================================================================
REM  install_toolcase.bat — ToolCase v5.4.1 Installatie voor Windows
REM  Valideert alle 60 tools, tests, SKILL.md, manifest.json en dashboard.
REM  Maker: SmokerGreenOG
REM =====================================================================
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║      ToolCase v5.4.1 — Installatie voor Windows            ║
echo ║      60 tools · 10 safety rules · recursive improvement    ║
echo ║      Maker: SmokerGreenOG                                  ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM ── Detect ToolCase directory ────────────────────────────────
set "TC_DIR=%~dp0"
if "%TC_DIR%"=="" set "TC_DIR=%CD%"
echo 📍 ToolCase directory: %TC_DIR%

REM ── Check Python ─────────────────────────────────────────────
echo.
echo 🔍 Checking Python...
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ Python niet gevonden. Installeer Python 3.11+ en probeer opnieuw.
    pause
    exit /b 1
)
python --version

REM ── Verify all .py files compile ─────────────────────────────
echo.
echo 🔍 Checking all Python files compile...
set ERRORS=0
for %%f in ("%TC_DIR%*.py") do (
    python -m py_compile "%%f" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo    ✅ %%~nxf
    ) else (
        echo    ❌ %%~nxf — COMPILE ERROR
        set /a ERRORS+=1
    )
)

if !ERRORS! gtr 0 (
    echo.
    echo ⚠  !ERRORS! bestand(en) hebben compile fouten.
) else (
    echo    ✅ Alle .py bestanden compileren zonder fouten!
)

REM ── Check tools_config.json ──────────────────────────────────
echo.
echo 🔍 Checking tools_config.json...
if exist "%TC_DIR%tools_config.json" (
    echo ✅ tools_config.json gevonden
) else (
    echo ⚠  tools_config.json niet gevonden
)

REM ── Check manifest.json ──────────────────────────────────────
echo.
echo 🔍 Checking manifest.json...
if exist "%TC_DIR%manifest.json" (
    python -c "import json; json.load(open(r'%TC_DIR%manifest.json'))" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo ✅ manifest.json — valid JSON
    ) else (
        echo ❌ manifest.json — invalid JSON
    )
) else (
    echo ⚠  manifest.json niet gevonden
)

REM ── Check SKILL.md ───────────────────────────────────────────
echo.
echo 🔍 Checking SKILL.md...
if exist "%TC_DIR%SKILL.md" (
    echo ✅ SKILL.md gevonden
) else (
    echo ⚠  SKILL.md niet gevonden
)

REM ── Check i18n ───────────────────────────────────────────────
echo.
echo 🔍 Checking i18n.py (EN/NL/DE)...
python -c "from i18n import t; print('   EN:', t('total_tools', lang='en')); print('   NL:', t('total_tools', lang='nl')); print('   DE:', t('total_tools', lang='de'))"

REM ── Check maker protection ───────────────────────────────────
echo.
echo 🔍 Checking maker protection...
python -c "from _protect import MAKER; print(f'   ✅ Maker: {MAKER}')"

REM ── Quick functional test ────────────────────────────────────
echo.
echo 🔍 Running quick functional test...
python "%TC_DIR%self_improve_loop.py" "%TC_DIR%" --cycles 1 --dry-run --json --no-report 2>&1 | findstr /C:"\"status\": \"passed\""
if %ERRORLEVEL% equ 0 (
    echo ✅ self_improve_loop.py — dry run OK
) else (
    echo ⚠  self_improve_loop.py — check output
)

REM ── Install Hermes skill (optional) ──────────────────────────
echo.
echo 🔍 Hermes skill installatie (optioneel)...
if exist "%USERPROFILE%\.hermes\skills\" (
    echo    Hermes skills directory gevonden
    if not exist "%USERPROFILE%\.hermes\skills\toolcase-self-improve\" (
        mkdir "%USERPROFILE%\.hermes\skills\toolcase-self-improve"
    )
    copy /Y "%TC_DIR%SKILL.md" "%USERPROFILE%\.hermes\skills\toolcase-self-improve\SKILL.md" >nul
    copy /Y "%TC_DIR%manifest.json" "%USERPROFILE%\.hermes\skills\toolcase-self-improve\manifest.json" >nul
    echo ✅ ToolCase skill geïnstalleerd voor Hermes!
    echo    Type: hermes -s toolcase-self-improve
) else (
    echo    ⚠  Hermes niet gevonden. Installeer Hermes Agent en draai dit script opnieuw.
    echo    Download: https://hermes-agent.nousresearch.com
)

REM ── FAIL GATE — abort if any critical check failed ──────────
echo.
if !ERRORS! gtr 0 (
    echo ╔══════════════════════════════════════════════════════════════╗
    echo ║      ❌ INSTALLATIE MISLUKT — !ERRORS! compile fout(en)      ║
    echo ╚══════════════════════════════════════════════════════════════╝
    pause
    exit /b 1
)
if not exist "%TC_DIR%tools_config.json" (
    echo ❌ tools_config.json ontbreekt — installatie mislukt.
    pause
    exit /b 1
)
if not exist "%TC_DIR%manifest.json" (
    echo ❌ manifest.json ontbreekt — installatie mislukt.
    pause
    exit /b 1
)
if not exist "%TC_DIR%SKILL.md" (
    echo ❌ SKILL.md ontbreekt — installatie mislukt.
    pause
    exit /b 1
)

REM ── Quick verify ────────────────────────────────────────────
echo 🔍 Quick verify: python improve.py --verify-install...
python "%TC_DIR%improve.py" --verify-install
if !ERRORLEVEL! neq 0 (
    echo ❌ verify-install mislukt.
    pause
    exit /b 1
)

REM ── Summary ──────────────────────────────────────────────────
echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║      ToolCase v5.4.1 — Installatie voltooid!               ║
echo ╠══════════════════════════════════════════════════════════════╣
echo ║  📍 %TC_DIR%                    ║
echo ║  🛠  60 tools · 10 safety rules                              ║
echo ║  🌐  EN/NL/DE i18n                                            ║
echo ║  ♻️  self_improve_loop.py — 13-step autonome workflow        ║
echo ║                                                              ║
echo ║  Quick start:                                                ║
echo ║    python improve.py --list-tools          (toon 60 tools)   ║
echo ║    python improve.py <bestand>             (check code)      ║
echo ║    python self_improve_loop.py --dry-run   (dry run)         ║
echo ║    python self_improve_loop.py --cycles 3  (auto-improve)    ║
echo ║                                                              ║
echo ║  Dashboard:                                                  ║
echo ║    python -m http.server 8080 --directory "%TC_DIR%"          ║
REM toolcase: ignore-security - expected local dashboard address
echo ║    http://localhost:8080/dashboard.html                       ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

pause
