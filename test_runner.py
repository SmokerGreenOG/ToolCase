#!/usr/bin/env python3
"""
test_runner.py — Discover and run tests in the project.

Discovers test files using common patterns and runs them automatically.
Supports pytest, unittest, Vitest, Jest, and Cargo test.

Gebruik:
    python test_runner.py <path>                         # Discover + run tests
    python test_runner.py <path> --dry-run               # Only discover, don't run
    python test_runner.py <path> --json                  # JSON output
    python test_runner.py <path> --verbose               # Verbose output
    python test_runner.py <path> --pattern *_test.py     # Custom pattern
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = frozenset({
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    ".tox", ".eggs", "build", "dist", ".next",
        ".backups",
        
        ".rsi_backups",
        
        ".rsi_reports",
        
        ".self_improve_reports",
        })

# Test file patterns per language
TEST_PATTERNS = {
    "python": {
        "patterns": ["test_*.py", "*_test.py", "*_tests.py", "test_*.py", "*test*.py"],
        "dirs": ["tests", "test"],
    },
    "typescript": {
        "patterns": ["*.test.ts", "*.test.tsx", "*.spec.ts",
                      "*.spec.tsx", "*.test.js", "*.spec.js",
                      "*.test.jsx", "*.spec.jsx"],
        "dirs": ["__tests__", "tests", "test"],
    },
    "rust": {
        "patterns": ["*.rs"],  # Inline tests in Rust
        "dirs": ["tests"],
    },
}

# Runner detection
RUNNER_DETECTION = {
    "pytest": {
        "config_files": ["pytest.ini", "pyproject.toml", "setup.cfg", "conftest.py"],
        "markers": ["pytest"],
        "command_template": "cd {workdir} && python -m pytest {test_files} {flags}",
    },
    "unittest": {
        "markers": ["unittest", "import unittest"],
        "command_template": "cd {workdir} && python -m unittest discover -s {test_dir} {flags}",
    },
    "vitest": {
        "config_files": ["vitest.config.ts", "vitest.config.js"],
        "markers": ["vitest"],
        "command_template": "cd {workdir} && npx vitest run {test_files} {flags}",
    },
    "jest": {
        "config_files": ["jest.config.ts", "jest.config.js", "jest.config.json"],
        "markers": ["jest"],
        "command_template": "cd {workdir} && npx jest {test_files} {flags}",
    },
    "cargo_test": {
        "config_files": ["Cargo.toml"],
        "markers": ["#[test]", "#[cfg(test)]"],
        "command_template": "cd {workdir} && cargo test {flags}",
    },
}

# Test detection heuristics per file type
TEST_FUNCTION_PATTERNS = {
    "python": [
        re.compile(r'def\s+test_\w+\s*\('),
        re.compile(r'class\s+Test\w+'),
        re.compile(r'@pytest\.'),
        re.compile(r'@mock\.'),
    ],
    "typescript": [
        re.compile(r'(?:describe|it|test)\s*\('),
        re.compile(r'(?:expect|assert)\s*\('),
    ],
    "rust": [
        re.compile(r'#\[test\]'),
        re.compile(r'#\[cfg\(test\)\]'),
        re.compile(r'assert_eq!|assert!|assert_ne!'),
    ],
}


def discover_tests(root: Path, pattern: str = None) -> list[dict]:
    """Discover test files in the project."""
    test_files = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        path = Path(dirpath)

        # Check patterns by language
        for lang, config in TEST_PATTERNS.items():
            test_dirs = config["dirs"]
            patterns = config["patterns"]

            # Check if we're in a test directory
            if path.name in test_dirs:
                for fn in filenames:
                    if any(fnmatch_simple(fn, p) for p in patterns):
                        fp = path / fn
                        test_files.append({
                            "file": str(fp),
                            "language": lang,
                            "dir": str(path.relative_to(root)),
                        })

            # Also check with custom pattern if provided
            if pattern:
                for fn in filenames:
                    if fnmatch_simple(fn, pattern):
                        fp = path / fn
                        test_files.append({
                            "file": str(fp),
                            "language": lang,
                            "dir": str(path.relative_to(root)),
                        })

    # Remove duplicates
    seen = set()
    unique = []
    for tf in test_files:
        if tf["file"] not in seen:
            seen.add(tf["file"])
            unique.append(tf)

    return sorted(unique, key=lambda x: x["file"])


def fnmatch_simple(filename: str, pattern: str) -> bool:
    """Simple fnmatch that handles * and ? without importing fnmatch."""
    # Convert glob pattern to regex
    regex_parts = []
    i = 0
    while i < len(pattern):
        if pattern[i] == '*':
            regex_parts.append('.*')
        elif pattern[i] == '?':
            regex_parts.append('.')
        elif pattern[i] in '.^$()+[]{}|\\':
            regex_parts.append('\\' + pattern[i])
        else:
            regex_parts.append(re.escape(pattern[i]))
        i += 1
    return bool(re.match('^' + ''.join(regex_parts) + '$', filename))


def detect_runner(root: Path, test_info: list[dict]) -> str:
    """Detect the most likely test runner."""
    scores = defaultdict(int)

    # Check config files
    for runner, config in RUNNER_DETECTION.items():
        for cf in config.get("config_files", []):
            if (root / cf).exists():
                scores[runner] += 2

        # Check if tests match this language
        ext_scores = {
            "pytest": [".py"],
            "unittest": [".py"],
            "vitest": [".ts", ".tsx", ".js", ".jsx", ".mjs"],
            "jest": [".ts", ".tsx", ".js", ".jsx", ".mjs"],
            "cargo_test": [".rs"],
        }

        for tf in test_info:
            fp = Path(tf["file"])
            ext = fp.suffix.lower()
            if ext in ext_scores.get(runner, []):
                scores[runner] += 1

    if not scores:
        # Default: prefer pytest if available, else unittest
        try:
            import pytest
            return "pytest"
        except ImportError:
            return "unittest"

    # Return highest-scoring runner
    best = max(scores, key=scores.get)
    
    # If pytest was selected but isn't installed, fallback to unittest
    if best == "pytest":
        try:
            import pytest
        except ImportError:
            if "unittest" in scores:
                return "unittest"
            return "unittest"  # Default fallback
    
    return best


def run_tests(workdir: Path, runner: str, test_files: list[dict],
              verbose: bool = False) -> dict:
    """Run tests using the detected runner."""
    test_paths = [tf["file"] for tf in test_files]
    flags = "-v" if verbose else ""

    template = RUNNER_DETECTION[runner].get("command_template", "")
    if not template:
        return {"success": False, "error": f"Onbekende runner: {runner}"}

    # Build command
    cmd_str = template.format(
        workdir=str(workdir),
        test_files=" ".join(test_paths),
        test_dir="tests",
        flags=flags,
    )

    start_time = datetime.now()

    try:
        cmd_args = shlex.split(cmd_str)
        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(workdir),
        )

        duration = (datetime.now() - start_time).total_seconds()

        # Parse test results from output
        passed = 0
        failed = 0
        skipped = 0
        errors = 0

        if runner in ("pytest", "unittest"):
            # Parse pytest output
            passed_match = re.search(r'(\d+)\s+passed', result.stdout)
            if passed_match:
                passed = int(passed_match.group(1))

            failed_match = re.search(r'(\d+)\s+failed', result.stdout)
            if failed_match:
                failed = int(failed_match.group(1))

            skipped_match = re.search(r'(\d+)\s+skipped', result.stdout)
            if skipped_match:
                skipped = int(skipped_match.group(1))

            error_match = re.search(r'(\d+)\s+error', result.stdout)
            if error_match:
                errors = int(error_match.group(1))

        elif runner in ("vitest", "jest"):
            passed_match = re.search(r'Tests:\s+(\d+)', result.stdout)
            if passed_match and "passed" in result.stdout:
                passed = int(passed_match.group(1))
            failed_match = re.search(r'(\d+)\s+failed', result.stdout)
            if failed_match:
                failed = int(failed_match.group(1))

        elif runner == "cargo_test":
            ok_match = re.search(r'(\d+)\s+passed', result.stdout)
            if ok_match:
                passed = int(ok_match.group(1))
            fail_match = re.search(r'(\d+)\s+failed', result.stdout)
            if fail_match:
                failed = int(fail_match.group(1))

        return {
            "success": result.returncode == 0,
            "runner": runner,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
            "duration": duration,
            "exit_code": result.returncode,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:1000],
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "runner": runner,
            "error": "Timeout na 10 minuten",
        }
    except Exception as e:
        return {
            "success": False,
            "runner": runner,
            "error": str(e),
        }


def print_test_report(test_info: list[dict], results: dict = None,
                      dry_run: bool = False) -> None:
    """Print formatted test discovery and run report."""
    by_lang = defaultdict(list)
    for tf in test_info:
        by_lang[tf["language"]].append(tf)

    total = len(test_info)
    print(f"\n{'='*60}")
    print(f" 🧪 TEST RUNNER")
    print(f"{'='*60}")
    print(f"   Test bestanden: {total}")
    for lang, files in sorted(by_lang.items()):
        print(f"   {lang}: {len(files)} bestand(en)")

    if dry_run:
        print(f"\n ── Gevonden Testbestanden ({total}) ──")
        for tf in test_info:
            print(f"   📄 {Path(tf['file']).relative_to(Path.cwd())}  [{tf['language']}]")
        return

    if results:
        print()
        print(f" ── Test Results ({results['runner']}) ──")
        if results["success"]:
            print(f"   ✅ ALL TESTS PASSED")
        else:
            print(f"   ❌ TESTS FAILED")

        print(f"   ✅ Passed:  {results.get('passed', results.get('success', 0))}")
        print(f"   ❌ Failed:  {results.get('failed', 0)}")
        print(f"   ⏭  Skipped: {results.get('skipped', 0)}")
        print(f"   ⚠  Errors:  {results.get('errors', 0)}")
        print(f"   ⏱  Duration: {results.get('duration', 0):.1f}s")

        if results.get("stdout"):
            # Show last relevant lines
            lines = results["stdout"].split("\n")
            relevant = [l for l in lines if l.strip() and not l.startswith((".", " ", "\t"))]
            for l in relevant[-10:]:
                print(f"   {l}")

        if not results["success"] and results.get("stderr"):
            print(f"\n   Stderr:")
            for l in results["stderr"].split("\n")[-5:]:
                if l.strip():
                    print(f"   {l}")

        if results.get("error"):
            print(f"\n   ❌ Fout: {results['error']}")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="test_runner.py — Discover and run tests in the project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python test_runner.py .                           # Discover + run
  python test_runner.py . --dry-run                 # Only discover
  python test_runner.py . --verbose                 # Verbose output
  python test_runner.py . --json                    # JSON output
  python test_runner.py . --pattern *_integration.py
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root")
    parser.add_argument("--dry-run", "-d", action="store_true",
                        help="Alleen test discovery, niet uitvoeren")
    parser.add_argument("--verbose", "-v", action="store_true", help="Uitgebreide output")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--pattern", "-p", help="Custom test file pattern")
    parser.add_argument("--version", action="version", version="test_runner.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 Test Runner v1.0.0 — scanning {target}")

    test_info = discover_tests(target, args.pattern)

    if not test_info:
        print(" Geen testbestanden gevonden")
        sys.exit(0)

    if args.dry_run:
        if args.json:
            print(json.dumps({"test_files": test_info, "dry_run": True}, indent=2))
        else:
            print_test_report(test_info, dry_run=True)
        return

    runner = detect_runner(target, test_info)
    print(f"   Runner: {runner}")

    results = run_tests(target, runner, test_info, args.verbose)

    if args.json:
        output = {
            "test_files": test_info,
            "runner": runner,
            "results": results,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print_test_report(test_info, results)

    if results and not results["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
