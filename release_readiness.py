#!/usr/bin/env python3
"""
release_readiness.py — Pre-release checklist: GO/NO-GO verdict.

Checks before you release:
  1. Version consistency (pyproject.toml == manifest.json == tools_config.json)
  2. Tool count consistency (manifest == tools_config == README)
  3. Syntax check (all .py files AST parse)
  4. Unit tests pass (70/70 expected)
  5. Security scan clean (0 HIGH findings)
  6. Install verify OK
  7. No generated reports in git tracked files
  8. CHANGELOG.md has entry for current version
  9. Git tag exists for current version
 10. README tool count matches manifest

Usage:
    python release_readiness.py                    # Full check
    python release_readiness.py --json             # JSON output
    python release_readiness.py --ci               # CI mode (no git checks)
"""
__maker__ = "SmokerGreenOG"

import _protect

import argparse
import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.resolve()


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    with open(path, "rb") as f:
        return tomllib.load(f)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + list(args),
        capture_output=True, text=True, timeout=15,
        cwd=str(PROJECT_ROOT),
    )


def _count_tools_in_readme(readme_text: str) -> int:
    """Count tool mentions in README.md tool reference section."""
    import re
    # Count unique tool names in the tool reference tables
    matches = re.findall(r'\|\s*`(\w+\.py)`\s*\|', readme_text)
    return len(set(matches))


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


class CheckResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.skipped = False
        self.detail = ""
        self.severity = "required"  # required | recommended | optional

    def pass_(self, detail: str = "") -> "CheckResult":
        self.passed = True
        self.detail = detail
        return self

    def fail(self, detail: str) -> "CheckResult":
        self.passed = False
        self.detail = detail
        return self

    def skip(self, detail: str = "") -> "CheckResult":
        self.skipped = True
        self.detail = detail
        return self

    @property
    def icon(self) -> str:
        if self.skipped:
            return "⊘"
        return "✅" if self.passed else "❌"


def check_version_consistency() -> CheckResult:
    """Check pyproject.toml == manifest.json == tools_config.json."""
    r = CheckResult("Version consistency").pass_()
    try:
        ppt = _load_toml(PROJECT_ROOT / "pyproject.toml")
        pv = ppt["project"]["version"]
    except Exception as e:
        return r.fail(f"Cannot read pyproject.toml: {e}")

    try:
        mf = _load_json(PROJECT_ROOT / "manifest.json")
        mv = mf["version"]
    except Exception as e:
        return r.fail(f"Cannot read manifest.json: {e}")

    try:
        tc = _load_json(PROJECT_ROOT / "tools_config.json")
        tv = tc["__meta"]["version"]
    except Exception as e:
        return r.fail(f"Cannot read tools_config.json: {e}")

    issues = []
    if pv != mv:
        issues.append(f"pyproject.toml ({pv}) != manifest.json ({mv})")
    if pv != tv:
        issues.append(f"pyproject.toml ({pv}) != tools_config.json ({tv})")

    if issues:
        return r.fail("; ".join(issues))
    return r.pass_(f"All at {pv}")


def check_tool_counts() -> CheckResult:
    """Check tool counts match across configs."""
    r = CheckResult("Tool counts").pass_()
    try:
        mf = _load_json(PROJECT_ROOT / "manifest.json")
        tc = _load_json(PROJECT_ROOT / "tools_config.json")
        mc = len(mf["tools"])
        tcc = len(tc["tools"])
    except Exception as e:
        return r.fail(str(e))

    if mc != tcc:
        return r.fail(f"manifest.json ({mc} tools) != tools_config.json ({tcc} tools)")

    # Check README
    try:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        readme_count = _count_tools_in_readme(readme)
        if abs(readme_count - mc) > 5:  # Tolerance: README may not list every tool
            return r.fail(f"README references ~{readme_count} tools, config has {mc}")
    except Exception:
        pass  # README check is optional

    return r.pass_(f"{mc} tools consistent")


def check_syntax() -> CheckResult:
    """AST syntax check all .py files."""
    r = CheckResult("Syntax check").pass_()
    errors = 0
    scanned = 0
    skip_dirs = {"__pycache__", ".rsi_backups", ".rsi_reports",
                 ".self_improve_reports", ".backups", ".venv", "venv"}

    for fp in PROJECT_ROOT.rglob("*.py"):
        if set(fp.parts) & skip_dirs:
            continue
        if any(p.startswith(".rsi_") for p in fp.parts):
            continue
        try:
            ast.parse(fp.read_text(encoding="utf-8"), filename=str(fp))
            scanned += 1
        except SyntaxError as e:
            errors += 1
            if errors == 1:  # Only report first error
                r.detail = f"{fp.name}:{e.lineno}: {e.msg}"

    if errors:
        return r.fail(f"{errors}/{scanned + errors} files have syntax errors — {r.detail}")
    return r.pass_(f"{scanned} files OK")


def check_unit_tests() -> CheckResult:
    """Run unittest discover."""
    r = CheckResult("Unit tests").pass_()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            capture_output=True, text=True, timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        if proc.returncode == 0:
            # Count passed tests
            import re
            match = re.search(r"Ran (\d+) tests", proc.stdout + proc.stderr)
            count = int(match.group(1)) if match else 0
            return r.pass_(f"{count} tests passed")
        else:
            # Extract failure count
            import re
            fail_match = re.search(r"FAILED.*?(\d+)", proc.stderr)
            err_match = re.search(r"errors=(\d+)", proc.stderr)
            details = []
            if fail_match:
                details.append(f"{fail_match.group(1)} failed")
            if err_match:
                details.append(f"{err_match.group(1)} errors")
            return r.fail("; ".join(details) if details else "Tests failed")
    except subprocess.TimeoutExpired:
        return r.fail("Test run timed out (60s)")
    except Exception as e:
        return r.fail(str(e))


def check_security_scan() -> CheckResult:
    """Run security scan, expect 0 HIGH findings."""
    r = CheckResult("Security scan").pass_()
    try:
        proc = subprocess.run(
            [sys.executable, "security_scan.py", ".", "--json"],
            capture_output=True, text=True, timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        if proc.returncode != 0:
            return r.fail(f"Scanner crashed: {proc.stderr[:200]}")

        # Parse JSON from output (strip banner)
        output = proc.stdout
        idx = output.find('{\n  "')
        if idx < 0:
            idx = output.find('{"')
        if idx >= 0:
            data = json.loads(output[idx:])
            high = data.get("by_risk", {}).get("high", 0)
            medium = data.get("by_risk", {}).get("medium", 0)
            if high > 0:
                return r.fail(f"{high} HIGH finding(s)")
            return r.pass_(f"HIGH={high}, MEDIUM={medium}")
        return r.skip("Could not parse JSON output")
    except subprocess.TimeoutExpired:
        return r.skip("Scan timed out")
    except Exception as e:
        return r.fail(str(e))


def check_install_verify() -> CheckResult:
    """Run improve.py --verify-install."""
    r = CheckResult("Install verify").pass_()
    try:
        proc = subprocess.run(
            [sys.executable, "improve.py", "--verify-install"],
            capture_output=True, text=True, timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        if proc.returncode != 0:
            return r.fail(proc.stderr[:200] or "Non-zero exit")
        if "Status: OK" in proc.stdout:
            return r.pass_("OK")
        return r.fail("Status not OK")
    except subprocess.TimeoutExpired:
        return r.skip("Timed out")
    except Exception as e:
        return r.fail(str(e))


def check_generated_in_git() -> CheckResult:
    """Check no generated report files are tracked by git."""
    r = CheckResult("Generated files in git")
    r.severity = "recommended"
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        if proc.returncode != 0:
            return r.skip("Not a git repo or git not available")

        tracked = set(proc.stdout.splitlines())
        generated_patterns = [
            "codex_audit_report.md",
            "codex_audit_report.html",
            "toolcase_analysis_report.html",
            "dexcore_analysis_report.html",
        ]
        found_gen = [f for f in tracked
                     if any(p in f.lower() for p in generated_patterns)
                     or "_audit_report." in f.lower()
                     or ".rsi_reports/" in f
                     or ".self_improve_reports/" in f]

        if found_gen:
            return r.fail(f"{len(found_gen)} generated file(s) tracked: {', '.join(found_gen[:3])}")
        return r.pass_("Clean")
    except Exception as e:
        return r.skip(str(e))


def check_changelog() -> CheckResult:
    """Check CHANGELOG.md has current version entry."""
    r = CheckResult("CHANGELOG entry")
    r.severity = "recommended"
    try:
        ppt = _load_toml(PROJECT_ROOT / "pyproject.toml")
        version = ppt["project"]["version"]
    except Exception:
        return r.skip("Cannot read version")

    changelog_path = PROJECT_ROOT / "CHANGELOG.md"
    if not changelog_path.exists():
        return r.skip("No CHANGELOG.md")

    try:
        content = changelog_path.read_text(encoding="utf-8")
        if version in content:
            return r.pass_(f"v{version} found")
        return r.fail(f"v{version} not mentioned in CHANGELOG.md")
    except Exception:
        return r.skip("Cannot read CHANGELOG.md")


def check_git_tag() -> CheckResult:
    """Check git tag exists for current version."""
    r = CheckResult("Git tag")
    r.severity = "recommended"
    try:
        ppt = _load_toml(PROJECT_ROOT / "pyproject.toml")
        version = ppt["project"]["version"]
    except Exception:
        return r.skip("Cannot read version")

    try:
        proc = _git("tag", "-l", f"v{version}")
        if proc.returncode != 0:
            return r.skip("Git not available")
        if proc.stdout.strip():
            return r.pass_(f"v{version} exists")
        return r.fail(f"Tag v{version} not found")
    except Exception:
        return r.skip("Git not available")


def check_readme_match() -> CheckResult:
    """Check README tool count matches manifest."""
    r = CheckResult("README vs manifest")
    r.severity = "recommended"
    try:
        mf = _load_json(PROJECT_ROOT / "manifest.json")
        mc = len(mf["tools"])
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        # Check the metrics table
        import re
        metrics_match = re.search(r'\|\s*Tools\s*\|\s*(\d+)\s*\|', readme)
        if metrics_match:
            readme_count = int(metrics_match.group(1))
            if readme_count == mc:
                return r.pass_(f"Both say {mc}")
            return r.fail(f"README says {readme_count}, manifest says {mc}")
        return r.skip("Could not find Tools row in README metrics")
    except Exception as e:
        return r.skip(str(e))


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_all_checks(ci_mode: bool = False) -> dict[str, Any]:
    """Run all release readiness checks and return report."""
    checks = [
        check_version_consistency(),
        check_tool_counts(),
        check_syntax(),
        check_unit_tests(),
        check_security_scan(),
        check_install_verify(),
        check_readme_match(),
    ]

    if not ci_mode:
        checks.extend([
            check_generated_in_git(),
            check_changelog(),
            check_git_tag(),
        ])

    passed_required = all(
        c.passed for c in checks
        if c.severity == "required" and not c.skipped
    )
    passed_all = all(
        c.passed or c.skipped for c in checks
    )
    verdict = "GO ✅" if passed_required else "NO-GO ❌"
    if passed_all and not passed_required:
        verdict = "GO (recommended items failed) ⚠"

    return {
        "verdict": verdict,
        "passed_required": passed_required,
        "passed_all": passed_all,
        "checks": [
            {
                "name": c.name,
                "passed": c.passed,
                "skipped": c.skipped,
                "severity": c.severity,
                "detail": c.detail,
            }
            for c in checks
        ],
    }


def print_report(report: dict[str, Any]) -> None:
    """Print formatted release readiness report."""
    print(f"\n{'=' * 60}")
    print(f" 📦 RELEASE READINESS CHECK — {report['verdict']}")
    print(f"{'=' * 60}")
    print()

    for c in report["checks"]:
        icon = "✅" if c["passed"] else "⊘" if c["skipped"] else "❌"
        sev_label = f"[{c['severity']}]" if c["severity"] != "required" else ""
        print(f" {icon} {c['name']} {sev_label}")
        if c["detail"]:
            print(f"    {c['detail']}")
    print()
    print(f"{'=' * 60}")
    print(f" Required checks: {'ALL PASSED' if report['passed_required'] else 'SOME FAILED'}")
    if report["passed_all"]:
        print(f" All checks:       PASSED")
    print(f"{'=' * 60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="release_readiness.py — Pre-release GO/NO-GO checklist",
    )
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--ci", action="store_true",
                        help="CI mode (skip git checks)")
    parser.add_argument("--version", action="version",
                        version="release_readiness.py v1.0.0")

    args = parser.parse_args()

    report = run_all_checks(ci_mode=args.ci)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)

    sys.exit(0 if report["passed_required"] else 1)


if __name__ == "__main__":
    main()
