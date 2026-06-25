#!/usr/bin/env python3
"""Auto-update README.md metrics from actual project scans.

Reads actual test count, Python file count, LOC, E501 count, and
updates the README metrics table in-place.

Usage:
    python scripts/sync_readme_metrics.py          # update README.md
    python scripts/sync_readme_metrics.py --check  # exit 1 if stale (CI mode)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


def count_tests() -> int:
    """Count actual tests via pytest --collect-only."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", str(ROOT / "tests"), "--collect-only", "-q"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ROOT),
        )
        # Parse "132 tests collected" or "collected 132 items"
        combined = r.stdout + r.stderr
        for line in combined.splitlines():
            m = re.search(r"(\d+) tests? collected", line.strip())
            if m:
                return int(m.group(1))
            m = re.search(r"collected (\d+) items?", line.strip())
            if m:
                return int(m.group(1))
        return 0
    except Exception:
        return 0


def count_py_files() -> int:
    """Count Python files excluding generated/backup dirs."""
    exclude = {".backups", ".rsi_backups", ".rsi_reports", "__pycache__", "build", "dist"}
    return len(
        [
            p
            for p in ROOT.rglob("*.py")
            if not (set(p.parts) & exclude)
            and ".egg-info" not in str(p)
        ]
    )


def count_loc() -> int:
    """Count lines of Python code."""
    exclude_dirs = {".backups", ".rsi_backups", ".rsi_reports", "__pycache__", "build", "dist"}
    total = 0
    for p in ROOT.rglob("*.py"):
        if set(p.parts) & exclude_dirs or ".egg-info" in str(p):
            continue
        try:
            total += len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
        except Exception:
            pass
    return total


def count_e501() -> int:
    """Count E501 violations via ruff if available."""
    import shutil

    ruff = None
    # Try Python 3.14 ruff first (where it's installed)
    for py in ["/c/Python314/python"]:
        try:
            r = subprocess.run(
                [py, "-m", "ruff", "--version"],
                capture_output=True, timeout=5,
            )
            if r.returncode == 0:
                ruff = [py, "-m", "ruff"]
                break
        except Exception:
            pass
    if not ruff:
        ruff_bin = shutil.which("ruff") or shutil.which("ruff.exe")
        if ruff_bin:
            ruff = [ruff_bin]
    if not ruff:
        return -1
    try:
        r = subprocess.run(
            ruff + ["check", "--select", "E501", "--line-length", "100", "--output-format", "concise", "."],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ROOT),
        )
        return len([l for l in r.stdout.splitlines() if "E501" in l])
    except Exception:
        return -1


def update_readme(check_only: bool = False) -> bool:
    """Update README metrics table. Returns True if changes were needed."""
    content = README.read_text(encoding="utf-8")

    tests = count_tests()
    py_files = count_py_files()
    loc = count_loc()
    e501 = count_e501()

    changes = 0

    # Unit tests
    new = re.sub(
        r"Unit tests\s*\|\s*\d+",
        f"Unit tests | {tests}",
        content,
    )
    if new != content:
        content = new
        changes += 1

    # Python files
    new = re.sub(
        r"Python files\s*\|\s*\d+",
        f"Python files | {py_files}",
        content,
    )
    if new != content:
        content = new
        changes += 1

    # Lines of code
    loc_str = f"{loc // 1000},{loc % 1000:03d}+" if loc > 1000 else str(loc)
    new = re.sub(
        r"Lines of code\s*\|\s*[\d,]+[\+]?",
        f"Lines of code | {loc_str}",
        content,
    )
    if new != content:
        content = new
        changes += 1

    # E501
    if e501 >= 0:
        e501_str = f"~{e501} (under active reduction)"
        new = re.sub(
            r"E501 long lines\s*\|\s*~?\d+.*",
            f"E501 long lines | {e501_str}",
            content,
        )
        if new != content:
            content = new
            changes += 1

    if check_only:
        if changes > 0:
            print(
                f"STALE: README metrics need update (tests={tests}, files={py_files}, loc={loc}, e501={e501})"
            )
            return False
        print(f"README metrics current: tests={tests}, files={py_files}, loc={loc}, e501={e501}")
        return True

    if changes > 0:
        README.write_text(content, encoding="utf-8")
        print(f"Updated README: {changes} metric(s) fixed")
    else:
        print("README metrics already current")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync README metrics from actual scans")
    parser.add_argument("--check", action="store_true", help="Exit 1 if stale (CI mode)")
    args = parser.parse_args()

    ok = update_readme(check_only=args.check)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
