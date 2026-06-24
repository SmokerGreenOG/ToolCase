#!/usr/bin/env python3
"""
Code Improvement Tool — laat Hermes code zelfstandig analyseren en verbeteren.

Gebruik:
    python improve.py <bestand>              # Enkel bestand verbeteren
    python improve.py <directory> --recursive  # Hele directory
    python improve.py --code "def foo():..."  # Code snippet direct

  Tools:
    python improve.py --security-scan <path>    # Security scan
    python improve.py --env-check <path>        # Environment check
    python improve.py --project-doctor <path>   # Project health
    python improve.py --route-scanner <path>    # Frontend routes
    python improve.py --fe-be-link <path>       # Frontend-backend koppeling
    python improve.py --dead-code <path>        # Dead code finder
    python improve.py --todo-tracker <path>     # TODO/FIXME tracker
    python improve.py --test-runner <path>      # Test runner
    python improve.py --patch-preview <file>    # Patch preview
    python improve.py --rollback <action> <target>  # Rollback
    python improve.py --dep-audit <path>        # Dependency audit
    python improve.py --workspace-index <path>  # Workspace index
    python improve.py --agent-memory <path>     # Agent state
    python improve.py --ui-consistency <path>   # UI consistency
    python improve.py --feature-gap <path>      # Feature gap analyzer
    python improve.py --multiscan <path>        # Multi-taal scan
    python improve.py --complexity <path>       # Complexiteitsanalyse
    python improve.py --depgraph <path>         # Dependency graph
    python improve.py --all <path>              # Alle tools tegelijk

  ToolCase v5.4.1:
    python improve.py --safe-run check <cmd>       # Guard: safe subprocess executor
    python improve.py --command-guard <cmd>      # Guard: command checker
    python improve.py --file-guard <path>        # Guard: file protection
    python improve.py --permission-audit         # Audit: agent perms
    python improve.py --api-contract <path>      # Analyze: API contracts
    python improve.py --fake-ui <path>           # Analyze: fake UI detector
    python improve.py --button-scan <path>       # Scan: button actions
    python improve.py --state-inspect <path>     # Analyze: state usage
    python improve.py --build-doctor <path>      # Execute: build diag
    python improve.py --log-viewer <path>        # Analyze: log viewer
    python improve.py --error-explain <txt>      # Analyze: error explainer
    python improve.py --release-package <path>   # Release: packager
    python improve.py --changelog <path>         # Analyze: changelog gen
    python improve.py --backup-mgr <a> <t>       # Backup: snapshot/restore
    python improve.py --docs-sync <path>         # Analyze: docs check
    python improve.py --skill-install <name>     # Skill: installer
    python improve.py --self-improve --target . --dry-run

  Extra:
    python improve.py --list-tools               # Toon alle 62 tools
    python improve.py --json-config              # Output tool config als JSON
    python improve.py --verify-install           # Controleer installatie

Dit bestand is het startpunt. Hermes kan dit bestand ZELF gebruiken
om zijn eigen code te verbeteren via de toolcase-self-improve skill.
"""

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from i18n import t, add_lang_arg, get_lang

# Ensure UTF-8 output on all platforms (Windows cp1252 can't handle emoji/unicode)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# ─────────────────────────────────────────────
# Documentatie helper — toon tool-overzicht
# ─────────────────────────────────────────────


def _show_tool_list(lang: str = "en") -> None:
    """Print a tool overview in the requested language."""
    cfg_path = _data_path("tools_config.json")
    if not cfg_path.exists():
        print(t("could_not_load_config", lang=lang))
        return

    with open(cfg_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    version = config["__meta"]["version"]
    tool_count = len(config["tools"])

    print("\n" + "=" * 60)
    print(t("toolcase_title", lang=lang, COUNT=tool_count, VERSION=version))
    print("=" * 60)
    print(f" {t('maker', lang=lang)}: {config['__meta']['maker']}")
    print(f" {t('version', lang=lang, VERSION=version)}")
    print()

    for cat in config["categories"]:
        tools_local = t("tools_visible", lang=lang, n=len(cat["tools"]))
        print(f" {cat['icon']}  {cat['name']} ({len(cat['tools'])} {tools_local.split()[-1]})")
        print(f"     {cat['description']}")
        for tool_name in cat["tools"]:
            tool = next((tdata for tdata in config["tools"] if tdata["name"] == tool_name), None)
            if not tool:
                continue
            risk_map = {"Low": "\U0001f7e2", "Medium": "\U0001f7e1", "High": "\U0001f534"}
            risk_icon = risk_map.get(tool["risk"], "\u26aa")
            tags_str = ", ".join(tool["tags"])
            print(f"     {tool['id']:2d}. {risk_icon} "
                  f"{tool['name']:<28s} {tool['type']:<9s} {tags_str}")
        print()

    print(f" {t('safety_rules_label', lang=lang)}: {len(config['safety_rules'])}")
    print(f" {t('ignored_dirs_label', lang=lang)}: {len(config['ignored_dirs'])}")
    print("=" * 60)


def _data_path(filename: str) -> Path:
    """Find a data file — local dir first, then installed wheel data dir."""
    local = Path(__file__).parent / filename
    if local.exists():
        return local
    # Check installed wheel data directory
    import sys
    for base in (sys.prefix, sys.base_prefix):
        candidate = Path(base) / "share" / "toolcase" / filename
        if candidate.exists():
            return candidate
    return local  # fallback to local path (will fail clearly if missing)


def _verify_install() -> bool:
    """Validate that the local ToolCase package is internally consistent."""
    root = Path(__file__).resolve().parent
    required = [
        "README.md",
        "SKILL.md",
        "manifest.json",
        "tools_config.json",
        "dashboard.html",
    ]
    errors = []
    warnings = []

    for name in required:
        if not _data_path(name).exists():
            errors.append(f"Missing required file: {name}")

    try:
        manifest = json.loads(_data_path("manifest.json").read_text(encoding="utf-8-sig"))
        config = json.loads(_data_path("tools_config.json").read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"Install check failed: {exc}")
        return False

    manifest_scripts = {tool.get("script") for tool in manifest.get("tools", [])}
    config_scripts = {tool.get("name") for tool in config.get("tools", [])}
    manifest_scripts.discard(None)
    config_scripts.discard(None)

    for script in sorted(manifest_scripts | config_scripts):
        if not (root / script).exists():
            errors.append(f"Missing tool script: {script}")

    missing_in_config = sorted(manifest_scripts - config_scripts)
    missing_in_manifest = sorted(config_scripts - manifest_scripts)
    if missing_in_config:
        errors.append("In manifest but not tools_config: " + ", ".join(missing_in_config))
    if missing_in_manifest:
        errors.append("In tools_config but not manifest: " + ", ".join(missing_in_manifest))

    if len(manifest_scripts) != len(config_scripts):
        errors.append(
            f"Tool count mismatch: manifest={len(manifest_scripts)}, "
            f"tools_config={len(config_scripts)}"
        )

    category_scripts = {
        script
        for category in config.get("categories", [])
        for script in category.get("tools", [])
    }
    uncategorized = sorted(config_scripts - category_scripts)
    if uncategorized:
        warnings.append("Configured but uncategorized: " + ", ".join(uncategorized))

    print("=" * 60)
    print("ToolCase install check")
    print("=" * 60)
    print(f"Root: {root}")
    print(f"Manifest tools:     {len(manifest_scripts)}")
    print(f"tools_config tools: {len(config_scripts)}")
    print(f"Categories:         {len(config.get('categories', []))}")

    # ── Validate that each configured command references an existing script ──
    command_issues = 0
    for tool in config.get("tools", []):
        cmd = tool.get("command", "")
        # Extract script name from command (e.g. "python command_guard.py <cmd>")
        parts = cmd.split()
        for part in parts:
            if part.endswith(".py") and not part.startswith("<"):
                script_path = root / part
                if not script_path.exists():
                    command_issues += 1
                    errors.append(f"Command '{tool.get('name','?')}' references missing script: {part}")
                break  # Only check first .py reference

    if command_issues:
        print(f"Command refs:        {command_issues} broken")
    else:
        print("Command refs:        all valid")

    for warning in warnings:
        print(f"WARN: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        print("Status: FAILED")
        return False

    print("Status: OK")
    return True


def syntax_check(filepath: str) -> tuple[bool, str]:
    """Controleer of een Python-bestand syntaxfouten bevat."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        ast.parse(source, filename=filepath)
        return True, "Syntax OK"
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"
    except Exception as e:
        return False, str(e)


def lint_check(filepath: str) -> list[str]:
    """Eenvoudige statische analyse zonder externe tools."""
    issues = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for i, line in enumerate(lines, 1):
            stripped = line.rstrip("\n")

            # Te lange regels
            if len(stripped) > 100:
                issues.append(
                    f"  {i:4d} | E501: Line too long ({len(stripped)} > 100)")

            # Trailing whitespace
            if stripped != stripped.rstrip():
                issues.append(f"  {i:4d} | W291: Trailing whitespace")

            # Check for comment markers — only in comments, not in code-strings
            is_lint_self = (
                "re." in stripped
                or "TODO|FIXME|HACK" in stripped
                or stripped.lstrip().startswith("# Zoek naar")
            )
            if not is_lint_self:
                cmt = re.search(r'#.*(TODO|FIXME|HACK)', stripped)
                if not cmt:
                    cmt = re.search(r'""".*?(TODO|FIXME|HACK)', stripped)
                if cmt:
                    issues.append(f"  {i:4d} | NOTE: Contains '{cmt.group(1)}'")

        # Hele bestand checks
        if not lines:
            issues.append("  ─    | Empty file")
        elif not lines[-1].endswith("\n"):
            issues.append(f"  {len(lines):4d} | W292: No newline at end of file")

    except Exception as e:
        issues.append(f"  ─    | Error reading file: {e}")

    return issues


def backup_file(filepath: str) -> str | None:
    """Maak een .bak backup van een bestand voor wijzigingen."""
    bak_path = filepath + ".bak"
    try:
        with open(filepath, "r", encoding="utf-8") as src:
            with open(bak_path, "w", encoding="utf-8") as bak:
                bak.write(src.read())
        return bak_path
    except Exception as e:
        print(f"  ⚠ Backup mislukt: {e}")
        return None


def count_lines(filepath: str) -> int:
    """Tel het aantal regels in een bestand."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def read_file_contents(filepath: str) -> Optional[str]:
    """Lees de inhoud van een bestand."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"  ⚠ Fout bij lezen {filepath}: {e}")
        return None


def analyze_file(filepath: str) -> dict:
    """Analyseer een enkel bestand en retourneer een rapport dict."""
    path = Path(filepath)
    if not path.exists():
        return {
            "file": filepath,
            "error": "Bestand niet gevonden",
            "issues": [],
            "syntax_ok": False,
        }

    if not path.is_file():
        return {"file": filepath, "error": "Geen bestand", "issues": [], "syntax_ok": False}

    syntax_ok, syntax_msg = syntax_check(filepath)
    issues = lint_check(filepath)

    # Langste regels vinden
    longest_lines = []
    with open(filepath, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if len(line.rstrip("\n")) > 80:
                longest_lines.append((i, len(line.rstrip("\n")), line.rstrip("\n")[:80]))
    longest_lines.sort(key=lambda x: x[1], reverse=True)

    line_count = count_lines(filepath)

    return {
        "file": filepath,
        "lines": line_count,
        "syntax_ok": syntax_ok,
        "syntax_msg": syntax_msg if not syntax_ok else None,
        "issues": issues,
        "longest_lines": longest_lines[:5],
        "error": None,
    }


def print_report(report: dict, verbose: bool = False, lang: str = "en") -> None:
    """Print a formatted report in the requested language."""
    file = report["file"]
    print(f"\n{'='*60}")
    print(t("file_report", lang=lang, file=file))
    print(f"{'='*60}")

    if report.get("error"):
        print(f" ❌ {report['error']}")
        return

    print(t("lines_count", lang=lang, n=report['lines']))
    print(f" {'✅' if report['syntax_ok'] else '❌'} ", end="")
    if report['syntax_ok']:
        print(t("syntax_ok", lang=lang))
    else:
        print(t("syntax_fail", lang=lang, msg=report['syntax_msg']))

    if report["issues"]:
        print(t("issues_found", lang=lang, n=len(report['issues'])))
        for issue in report["issues"]:
            print(issue)

    if report["longest_lines"]:
        print(t("longest_lines", lang=lang))
        for line_no, length, snippet in report["longest_lines"]:
            print(f"   L{line_no}: {length} chars  →  {snippet}")

    if not report["issues"] and report["syntax_ok"]:
        print(t("looks_good", lang=lang))


def find_python_files(directory: str, recursive: bool = False) -> list[str]:
    """Vind Python-bestanden in een directory."""
    path = Path(directory)
    if not path.exists() or not path.is_dir():
        return []

    ignored_dirs = {
        "node_modules", ".git", "dist", "build", ".next", "out",
        "coverage", ".venv", "venv", "__pycache__", ".pytest_cache",
        ".cache", ".backups", ".self_improve_reports", "release",
    }

    def is_in_ignored_dir(candidate: Path) -> bool:
        """Check if in ignored dir.

            Args:
                candidate: Description.

            Returns:
                Description.
            """
        try:
            rel_parts = candidate.relative_to(path).parts
        except ValueError:
            rel_parts = candidate.parts
        return any(part in ignored_dirs for part in rel_parts)

    if recursive:
        return sorted(str(p) for p in path.rglob("*.py") if not is_in_ignored_dir(p))
    else:
        return sorted(str(p) for p in path.glob("*.py") if not is_in_ignored_dir(p))


def process_snippet(snippet: str) -> dict:
    """Analyseer een code snippet (schrijf tijdelijk weg)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(snippet)
        tmp_path = f.name

    report = analyze_file(tmp_path)
    report["file"] = "<snippet>"  # Toon als snippet
    os.unlink(tmp_path)
    return report


# ── Exit codes (machine-readable contract) ────────────
EXIT_OK = 0       # Success, no issues found
EXIT_FINDINGS = 1  # Issues/findings detected
EXIT_ERROR = 2     # Invalid input, syntax error, or internal error


def main() -> int:
    """main — returns exit code: 0=clean, 1=findings, 2=error.
        """
    parser = argparse.ArgumentParser(
        description="Code Improvement Tool — Analyseer en verbeter code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Voorbeelden:
  python improve.py script.py                    # Enkel bestand
  python improve.py src/ --recursive             # Hele directory
  python improve.py --code "def foo(): pass"     # Code snippet
  python improve.py --auto-fix script.py         # Analyseer + automatisch fixen
  python improve.py --list-tools                 # Toon alle 60 tools
  python improve.py --json-config                # Output tool config als JSON
  python improve.py --verify-install             # Controleer installatie
        """,
    )
    parser.add_argument("target", nargs="?", help="Bestand of directory om te analyseren")
    parser.add_argument("--code", "-c", help="Code snippet direct analyseren")
    parser.add_argument("--recursive", "-r", action="store_true",
                        help="Recursief door directories")
    parser.add_argument("--verbose", "-v", action="store_true", help="Uitgebreide uitvoer")
    parser.add_argument("--auto-fix", "-f", action="store_true",
                        help="Probeer automatisch te fixen")
    parser.add_argument("--version", action="version", version="improve.py v5.4.1")
    parser.add_argument("--list-tools", action="store_true",
                        help="Toon alle beschikbare tools in de ToolCase")
    parser.add_argument("--json-config", action="store_true",
                        help="Output tool configuratie als JSON")
    parser.add_argument("--verify-install", action="store_true",
                        help="Controleer of ToolCase correct is geinstalleerd")

    # Legacy tools
    parser.add_argument("--multiscan", "-m", metavar="PATH",
                        help="Multi-taal scan: detecteer issues in .py/.ts/.tsx/.rs bestanden")
    parser.add_argument("--complexity", "-x", metavar="PATH",
                        help="Cyclomatische complexiteitsanalyse van functies")
    parser.add_argument("--depgraph", "-d", metavar="PATH",
                        help="Import/export dependency graph van de codebase")
    parser.add_argument("--all", "-a", metavar="PATH",
                        help="Draai alle tools tegelijk")

    # Bestaande v2 tools
    parser.add_argument("--security-scan", metavar="PATH",
                        help="Security scan: detecteer hardcoded secrets en risico's")
    parser.add_argument("--env-check", metavar="PATH",
                        help="Environment check: controleer env variabelen en config")
    parser.add_argument("--project-doctor", metavar="PATH",
                        help="Project doctor: diagnoseer project gezondheid")
    parser.add_argument("--route-scanner", metavar="PATH",
                        help="Route scanner: vind frontend routes en navigatie")
    parser.add_argument("--fe-be-link", metavar="PATH",
                        help="Frontend-backend linker: cross-ref API endpoints")
    parser.add_argument("--dead-code", metavar="PATH",
                        help="Dead code finder: vind ongebruikte imports/functies")
    parser.add_argument("--todo-tracker", metavar="PATH",
                        help="TODO tracker: scan voor TODO/FIXME/HACK markers")
    parser.add_argument("--test-runner", metavar="PATH",
                        help="Test runner: discover en run tests")
    parser.add_argument("--patch-preview", metavar="FILE",
                        help="Patch preview: toon diff voor wijzigingen")
    parser.add_argument("--rollback", nargs=2, metavar=("ACTION", "TARGET"),
                        help="Rollback: herstel .bak backups")
    parser.add_argument("--dep-audit", metavar="PATH",
                        help="Dependency audit: check dependency status")
    parser.add_argument("--workspace-index", metavar="PATH",
                        help="Workspace index: indexeer en analyseer workspace")
    parser.add_argument("--agent-memory", metavar="PATH",
                        help="Agent memory: toon Hermes agent state")
    parser.add_argument("--ui-consistency", metavar="PATH",
                        help="UI consistency: check UI patroon consistentie")
    parser.add_argument("--feature-gap", metavar="PATH",
                        help="Feature gap analyzer: vind frontend/backend gaten")

    # ToolCase v5.4.1 tools
    parser.add_argument("--command-guard", metavar="CMD",
                        help="Guard: controleer terminal commands op veiligheid")
    parser.add_argument("--safe-run", nargs="+", metavar=("CMD", "ARGS"),
                        help="Guard: veilige subprocess executor met workspace containment")
    parser.add_argument("--file-guard", metavar="FILE",
                        help="Guard: bescherm belangrijke bestanden tegen overschrijven")
    parser.add_argument("--permission-audit", action="store_true",
                        help="Audit: controleer agent permissies")
    parser.add_argument("--api-contract", metavar="PATH",
                        help="Analyze: controleer frontend-backend API contracten")
    parser.add_argument("--fake-ui", metavar="PATH",
                        help="Analyze: detecteer fake/demo UI in projecten")
    parser.add_argument("--button-scan", metavar="PATH",
                        help="Scan: zoek buttons/forms zonder echte actie")
    parser.add_argument("--state-inspect", metavar="PATH",
                        help="Analyze: inspecteer React/Vue/Svelte state usage")
    parser.add_argument("--build-doctor", metavar="PATH",
                        help="Execute: diagnosticeer build problemen")
    parser.add_argument("--log-viewer", metavar="PATH",
                        help="Analyze: vind logs en vat errors samen")
    parser.add_argument("--error-explain", metavar="ERROR",
                        help="Analyze: vertaal error/traceback naar uitleg + fix")
    parser.add_argument("--release-package", metavar="PATH",
                        help="Release: maak release package met checks")
    parser.add_argument("--changelog", metavar="PATH",
                        help="Analyze: genereer changelog uit git/patch history")
    parser.add_argument("--backup-mgr", nargs=2, metavar=("ACTION", "TARGET"),
                        help="Backup: beheer snapshots en backups (snapshot|restore|list|diff)")
    parser.add_argument("--docs-sync", metavar="PATH",
                        help="Analyze: check of README/docs kloppen met code")
    parser.add_argument("--skill-install", metavar="SKILL",
                        help="Skill: installeer en valideer Hermes/Sabine skill")
    parser.add_argument("--php-check", metavar="PATH",
                        help="Scan: PHP code quality & security checker")

    parser.add_argument("--php-complexity", metavar="PATH",
                        help="Analyze: PHP cyclomatic complexity")
    parser.add_argument("--php-depgraph", metavar="PATH",
                        help="Analyze: PHP dependency graph")
    parser.add_argument("--php-dead-code", metavar="PATH",
                        help="Analyze: PHP dead code finder")
    parser.add_argument("--php-config-audit", metavar="PATH",
                        help="Security: PHP config audit (php.ini, .env, .htaccess)")
    parser.add_argument("--php-version-audit", metavar="PATH",
                        help="Compat: PHP version compatibility check")
    parser.add_argument("--php-test-runner", metavar="PATH",
                        help="Execute: PHP test runner (PHPUnit/Pest)")
    parser.add_argument("--php-dep-audit", metavar="PATH",
                        help="Security: Composer dependency auditor")
    parser.add_argument("--apk-reverse", metavar="APK",
                        help="Reverse: Android APK reverse engineering & decompilation")

    # Self-improvement workflow
    parser.add_argument("--self-improve", action="store_true",
                        help="♻️  Self-improve: 13-step autonome verbeteringsloop")
    parser.add_argument("--target", dest="self_target",
                        help="Workspace path voor --self-improve")
    parser.add_argument("--dry-run", action="store_true",
                        help="Self-improve analyse only; wijzig geen bestanden")
    parser.add_argument("--apply", action="store_true",
                        help="Self-improve apply mode met backup/test/rollback")
    parser.add_argument("--safe-only", action="store_true",
                        help="Self-improve safe-only mode")
    parser.add_argument("--cycles", type=int,
                        help="Aantal self-improve cycli")
    parser.add_argument("--focus",
                        choices=["all", "docs", "security", "code-quality", "tests"],
                        help="Focus voor self-improve")
    parser.add_argument("--json", action="store_true",
                        help="Self-improve output als JSON")

    # ── Language flag ──────────────────────────────────────
    add_lang_arg(parser)

    args = parser.parse_args()
    lang = args.lang if hasattr(args, 'lang') else get_lang()

    # ── Speciale opties ───────────────────────────────────
    if args.list_tools:
        _show_tool_list(lang)
        return EXIT_OK

    if args.json_config:
        cfg_path = _data_path("tools_config.json")
        if cfg_path.exists():
            print(cfg_path.read_text(encoding="utf-8"))
        else:
            print('{"error": "tools_config.json not found"}')
        return EXIT_OK

    if args.verify_install:
        ok = _verify_install()
        sys.exit(0 if ok else 1)

    # ── CHEATSHEET ────────────────────────────────────────
    tool_flags = [
        args.multiscan, args.complexity, args.depgraph, args.all,
        args.security_scan, args.env_check, args.project_doctor,
        args.route_scanner, args.fe_be_link, args.dead_code,
        args.todo_tracker, args.test_runner, args.patch_preview,
        args.rollback, args.dep_audit, args.workspace_index,
        args.agent_memory, args.ui_consistency, args.feature_gap,
        args.command_guard, args.file_guard, args.permission_audit,
        args.safe_run,
        args.api_contract, args.fake_ui, args.button_scan,
        args.state_inspect, args.build_doctor, args.log_viewer,
        args.error_explain, args.release_package, args.changelog,
        args.backup_mgr, args.docs_sync, args.skill_install,
        args.php_check,
        args.php_complexity, args.php_depgraph, args.php_dead_code,
        args.php_config_audit, args.php_version_audit,
        args.php_test_runner, args.php_dep_audit,
        args.apk_reverse,
        args.self_improve,
    ]

    if args.target is None and args.code is None and not any(tool_flags):
        parser.print_help()
        print("\n" + "=" * 60)
        print(t("hermes_hint", lang=lang))
        print("=" * 60)
        print(f"\n{t('workflow_title', lang=lang, VERSION='5.4.1')}\n")
        print(t("workflow_step1", lang=lang))
        print(t("workflow_step2", lang=lang))
        print(t("workflow_step3", lang=lang))
        print(f"\n{t('workflow_loop_hint', lang=lang)}")
        print(f"\n{t('workflow_self_hint', lang=lang)}")
        return EXIT_ERROR

    # ── Tool dispatcher ──────────────────────────────────
    tool_path = Path(__file__).parent
    _last_exit_code = 0

    def _run_script(script_name: str, *extra_args: str) -> int:
        """Run a tool script and return its exit code."""
        nonlocal _last_exit_code
        cmd = [sys.executable, str(tool_path / script_name)] + list(extra_args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        print(result.stdout)
        if result.returncode != 0 and result.stderr.strip():
            print(f" {t('exit_code', lang=lang, code=result.returncode)} | {result.stderr[:300]}",
                  file=sys.stderr)
        if result.returncode != 0:
            _last_exit_code = result.returncode
        return result.returncode

    # Legacy tools
    if args.multiscan:
        if not Path(args.multiscan).exists():
            print(t("file_not_found", lang=lang, target=args.multiscan)); sys.exit(2)
        print(f"\n{'='*60}\n 🛠  MULTISCAN — {args.multiscan}\n{'='*60}")
        _run_script("multiscan.py", args.multiscan)
        sys.exit(_last_exit_code)

    if args.complexity:
        if not Path(args.complexity).exists():
            print(t("file_not_found", lang=lang, target=args.complexity)); sys.exit(2)
        print(f"\n{'='*60}\n 📏 COMPLEXITEIT — {args.complexity}\n{'='*60}")
        _run_script("complexity.py", args.complexity)
        sys.exit(_last_exit_code)

    if args.depgraph:
        if not Path(args.depgraph).exists():
            print(t("file_not_found", lang=lang, target=args.depgraph)); sys.exit(2)
        print(f"\n{'='*60}\n 🔗 DEPGRAPH — {args.depgraph}\n{'='*60}")
        _run_script("depgraph.py", args.depgraph)
        sys.exit(_last_exit_code)

    # Bestaande v2 tools
    extra_tools = {
        "security_scan": ("security_scan.py", []),
        "env_check": ("env_check.py", []),
        "project_doctor": ("project_doctor.py", []),
        "route_scanner": ("route_scanner.py", []),
        "fe_be_link": ("frontend_backend_linker.py", []),
        "dead_code": ("dead_code_finder.py", []),
        "todo_tracker": ("todo_tracker.py", []),
        "test_runner": ("test_runner.py", []),
        "patch_preview": ("patch_preview.py", []),
        "dep_audit": ("dependency_audit.py", []),
        "workspace_index": ("workspace_indexer.py", []),
        "agent_memory": ("agent_memory.py", []),
        "ui_consistency": ("ui_consistency.py", []),
        "feature_gap": ("feature_gap_analyzer.py", []),
    }

    for flag, (script, extra) in extra_tools.items():
        val = getattr(args, flag, None)
        if val:
            target = str(val)
            if not Path(target).exists():
                print(t("file_not_found", lang=lang, target=target))
                sys.exit(2)  # Input error, not findings
            print(f"\n{'='*60}\n 🛠  {script.replace('.py','').upper()} — {target}\n{'='*60}")
            _run_script(script, target)
            sys.exit(_last_exit_code)

    if args.rollback:
        action, target = args.rollback
        print(f"\n{'='*60}\n 🔄 ROLLBACK {action} — {target}\n{'='*60}")
        _run_script("rollback.py", action, target)
        sys.exit(_last_exit_code)

    # ToolCase v5.4.1 dispatcher
    new_tools = [
        ("command_guard", "command_guard.py", False),
        ("safe_run", "safe_run.py", False),
        ("file_guard", "file_guard.py", False),
        ("permission_audit", "permission_audit.py", True),
        ("api_contract", "api_contract_checker.py", False),
        ("fake_ui", "fake_ui_detector.py", False),
        ("button_scan", "button_action_scanner.py", False),
        ("state_inspect", "state_inspector.py", False),
        ("build_doctor", "build_doctor.py", False),
        ("log_viewer", "log_viewer.py", False),
        ("error_explain", "error_explainer.py", False),
        ("release_package", "release_packager.py", False),
        ("changelog", "changelog_generator.py", False),
        ("backup_mgr", "backup_manager.py", False),
        ("docs_sync", "docs_sync.py", False),
        ("skill_install", "skill_installer.py", False),
        ("php_check", "php_checker.py", False),
        ("php_complexity", "php_complexity.py", False),
        ("php_depgraph", "php_depgraph.py", False),
        ("php_dead_code", "php_dead_code.py", False),
        ("php_config_audit", "php_config_audit.py", False),
        ("php_version_audit", "php_version_audit.py", False),
        ("php_test_runner", "php_test_runner.py", False),
        ("php_dep_audit", "php_dep_audit.py", False),
        ("apk_reverse", "apk_reverse.py", False),
    ]
    for arg_name, script_name, is_flag in new_tools:
        val = getattr(args, arg_name, None)
        if val:
            icon_map = {
                "command_guard": "🔒 COMMAND GUARD",
                "safe_run": "\U0001f6e1\ufe0f SAFE RUN",
                "file_guard": "📁 FILE GUARD",
                "permission_audit": "🔐 PERMISSION AUDIT",
                "api_contract": "🔗 API CONTRACT CHECKER",
                "fake_ui": "🎭 FAKE UI DETECTOR",
                "button_scan": "🔘 BUTTON ACTION SCANNER",
                "state_inspect": "🧠 STATE INSPECTOR",
                "build_doctor": "🏗 BUILD DOCTOR",
                "log_viewer": "📋 LOG VIEWER",
                "error_explain": "❓ ERROR EXPLAINER",
                "release_package": "📦 RELEASE PACKAGER",
                "changelog": "📝 CHANGELOG GENERATOR",
                "backup_mgr": "💾 BACKUP MANAGER",
                "docs_sync": "📚 DOCS SYNC",
                "skill_install": "🧩 SKILL INSTALLER",
                "php_check": "🐘 PHP CHECKER",
                "php_complexity": "📏 PHP COMPLEXITY",
                "php_depgraph": "🔗 PHP DEPGRAPH",
                "php_dead_code": "💀 PHP DEAD CODE",
                "php_config_audit": "⚙ PHP CONFIG AUDIT",
                "php_version_audit": "📅 PHP VERSION AUDIT",
                "php_test_runner": "🧪 PHP TEST RUNNER",
                "php_dep_audit": "📦 PHP DEP AUDIT",
                "apk_reverse": "🔍 APK REVERSE",
            }
            title = icon_map.get(arg_name, script_name.replace('.py', '').upper())
            print(f"\n{'='*60}\n {title}\n{'='*60}")

            if arg_name == "backup_mgr":
                _run_script(script_name, val[0], val[1])
            elif arg_name == "safe_run":
                _run_script(script_name, *val)
            elif is_flag:
                _run_script(script_name)
            else:
                _run_script(script_name, str(val))
            sys.exit(_last_exit_code)

    # Dispatch self_improve_loop.py (standalone workflow)
    if args.self_improve:
        script = Path(__file__).parent / "self_improve_loop.py"
        print(f"\n{'='*60}\n ♻️  SELF-IMPROVE LOOP — 13-step autonome verbeteringsloop\n{'='*60}")
        sys.stdout.flush()
        target = args.self_target or args.target or "."
        cmd = [sys.executable, str(script), target]
        if args.dry_run:
            cmd.append("--dry-run")
        if args.apply:
            cmd.append("--apply")
        if args.safe_only:
            cmd.append("--safe-only")
        if args.cycles is not None:
            cmd.extend(["--cycles", str(args.cycles)])
        if args.focus:
            cmd.extend(["--focus", args.focus])
        if args.json:
            cmd.append("--json")
        result = subprocess.run(cmd, timeout=300)
        sys.exit(result.returncode)

    if args.all:
        target = args.all
        if not Path(target).exists():
            print(t("file_not_found", lang=lang, target=target))
            sys.exit(2)
        for tool_name, tool_script in [
            ("MULTISCAN", "multiscan.py"),
            ("COMPLEXITEIT", "complexity.py"),
            ("DEPGRAPH", "depgraph.py"),
            ("SECURITY SCAN", "security_scan.py"),
            ("ENV CHECK", "env_check.py"),
            ("PROJECT DOCTOR", "project_doctor.py"),
        ]:
            print(f"\n{'='*60}\n 🛠  {tool_name} — {target}\n{'='*60}")
            _run_script(tool_script, target)
        sys.exit(_last_exit_code)

    # ── Analyse modus ─────────────────────────────────────
    print(t("code_improvement_tool", lang=lang, VERSION="5.4.1"))
    print(f"{'='*60}")

    if args.code:
        report = process_snippet(args.code)
        print_report(report, args.verbose, lang)
        return EXIT_FINDINGS if report.get("issues") else EXIT_OK

    target = args.target
    path = Path(target)

    if path.is_file():
        if not target.endswith(".py"):
            print(t("not_python_file", lang=lang, target=target))
            return EXIT_ERROR
        report = analyze_file(target)
        print_report(report, args.verbose, lang)

        if args.auto_fix and not report["syntax_ok"]:
            print(t("auto_fix_mode", lang=lang))

        has_issues = len(report.get("issues", [])) > 0 or not report.get("syntax_ok", True)
        return EXIT_FINDINGS if has_issues else EXIT_OK

    elif path.is_dir():
        files = find_python_files(target, args.recursive)
        if not files:
            print(t("no_python_files", lang=lang, target=target))
            return EXIT_ERROR

        print(t("files_found", lang=lang, n=len(files), target=target))
        total_issues = 0
        all_ok = True
        reports = []

        for f in files:
            report = analyze_file(f)
            reports.append(report)
            print_report(report, args.verbose, lang)
            total_issues += len(report["issues"])
            if not report["syntax_ok"]:
                all_ok = False

        print(f"\n{'='*60}")
        print(t("summary_title", lang=lang))
        print(f"{'='*60}")
        lang_syntax = t("syntax_all_ok", lang=lang) if all_ok else t("syntax_some_fail", lang=lang)
        print(f" {t('files_scanned', lang=lang, n=len(files))} — {lang_syntax}")
        print(f" ⚠  {t('issues_found', lang=lang, n=total_issues)}")
        if total_issues > 0:
            print(f"\n{t('loop_hint_summary', lang=lang)}")
        return EXIT_FINDINGS if (total_issues > 0 or not all_ok) else EXIT_OK
    else:
        print(t("file_not_found", lang=lang, target=target))
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
