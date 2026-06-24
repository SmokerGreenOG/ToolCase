#!/usr/bin/env python3
"""
git_workflow_checker.py — Check Git workflow quality.

Checkt:
  - Conventional Commits format
  - Branch naming conventions
  - .gitignore completeness
  - Uncommitted changes
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

CONVENTIONAL_PATTERN = re.compile(
    r'^(?:feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)'
    r'(?:\([^)]+\))?!?:\s.+'
    r'|^(?:Merge|Revert)'
    r'|^[🎉✨🔧📝🧪♻️🔒🐛📊🔗🛡️🩺🌐🚀📦💾👷📚🟢🟡🔴✅]'
)

BRANCH_PATTERNS = {
    "main": r'^(?:main|master)$',
    "feature": r'^(?:feature|feat)/',
    "bugfix": r'^(?:bugfix|fix|hotfix)/',
    "release": r'^(?:release|rel)/',
}


def run_git(cmd: list[str]) -> tuple[str, str, int]:
    """Run git.

        Args:
            cmd: Description.

        Returns:
            Description.
        """
    r = subprocess.run(
        ["git"] + cmd,
        capture_output=True, text=True, cwd=str(ROOT)
    )
    return r.stdout, r.stderr, r.returncode


def check() -> dict:
    """check.
        """
    errors, warnings, ok = [], [], []

    # Check if git repo
    if not (ROOT / ".git").exists():
        errors.append("Geen git repository")
        return {"errors": errors, "warnings": warnings, "ok": ok}
    ok.append("Git repository ✅")

    # Branch name
    out, _, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    branch = out.strip()
    if any(re.match(p, branch) for p in BRANCH_PATTERNS.values()):
        ok.append(f"Branch: '{branch}' ✅")
    else:
        warnings.append(f"Branch '{branch}' niet in standaard patterns")

    # Commits check
    out, _, _ = run_git(["log", "--oneline", "-20"])
    commits = [l.split(" ", 1)[1] if " " in l else l for l in out.strip().split("\n") if l]
    bad_commits = [c[:70] for c in commits if not CONVENTIONAL_PATTERN.match(c)]
    if bad_commits:
        warnings.append(f"{len(bad_commits)}/{len(commits)} non-conventional commits")
        for c in bad_commits[:3]:
            warnings.append(f"  → {c[:70]}")
    else:
        ok.append(f"All {len(commits)} commits conventional ✅")

    # Uncommitted changes
    out, _, _ = run_git(["status", "--porcelain"])
    dirty = [l for l in out.strip().split("\n") if l]
    if dirty:
        warnings.append(f"{len(dirty)} uncommitted changes")
    else:
        ok.append("Working tree clean ✅")

    # .gitignore check
    gi = ROOT / ".gitignore"
    if gi.exists():
        patterns = gi.read_text().splitlines()
        count = sum(1 for p in patterns if p.strip() and not p.startswith("#"))
        ok.append(f".gitignore: {count} patterns")
        # Check for common misses
        needed = [(".env", ".env"), ("*.bak", "*.bak"), ("__pycache__", "__pycache__")]
        for pat, desc in needed:
            if not any(pat in p for p in patterns):
                warnings.append(f".gitignore mist: {desc}")
    else:
        errors.append(".gitignore ontbreekt")

    return {"errors": errors, "warnings": warnings, "ok": ok}


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(description="Git Workflow Checker")
    parser.add_argument("--json", "-j", action="store_true")
    args = parser.parse_args()

    report = check()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print()
        print("=" * 50)
        print(" 🔍 GIT WORKFLOW CHECKER")
        print("=" * 50)
        for line in report["ok"]:
            print(f"   ✅ {line}")
        for line in report["warnings"]:
            print(f"   ⚠️  {line}")
        for line in report["errors"]:
            print(f"   ❌ {line}")

        status = "❌ FAIL" if report["errors"] else "⚠️ WARN" if report["warnings"] else "✅ ALL OK"
        print()
        print(f"   Status: {status}")
        print()

    sys.exit(1 if report["errors"] else 0)


if __name__ == "__main__":
    main()
