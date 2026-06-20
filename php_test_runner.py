#!/usr/bin/env python3
"""
php_test_runner.py — PHP test discovery & execution.

Discover en run PHP tests:
  - PHPUnit (phpunit.xml/phpunit.xml.dist config)
  - Pest (tests/Pest.php config)
  - Standalone test files
  - Coverage reports

Gebruik:
    python php_test_runner.py <path>
    python php_test_runner.py <path> --filter TestName
    python php_test_runner.py <path> --coverage
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXCLUDE_DIRS = {"node_modules", "vendor", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".cache"}

PHP = shutil.which("php")
PHPUNIT = shutil.which("phpunit")
PEST = shutil.which("pest")


def discover_test_files(root: Path) -> dict:
    """Discover PHPUnit/Pest test configuration and test files."""
    result = {
        "framework": "unknown",
        "config_file": None,
        "test_files": [],
        "test_count": 0,
    }

    # Check for phpunit.xml / phpunit.xml.dist
    for config_name in ["phpunit.xml", "phpunit.xml.dist"]:
        cfg = root / config_name
        if cfg.exists():
            result["config_file"] = str(cfg)
            result["framework"] = "phpunit"
            try:
                tree = ET.parse(cfg)
                for ts in tree.findall(".//testsuite"):
                    for directory in ts.findall("directory"):
                        dir_path = root / directory.text
                        if dir_path.exists():
                            for f in dir_path.rglob("*Test.php"):
                                result["test_files"].append(str(f))
                            for f in dir_path.rglob("test_*.php"):
                                result["test_files"].append(str(f))
            except:
                pass
            break

    # Check for Pest
    pest_cfg = root / "tests" / "Pest.php"
    if pest_cfg.exists() and not result["config_file"]:
        result["framework"] = "pest"
        result["config_file"] = str(pest_cfg)

    # Fallback: scan for test files
    if not result["test_files"]:
        tests_dir = root / "tests"
        if tests_dir.exists():
            for f in tests_dir.rglob("*Test.php"):
                try:
                    parts = f.relative_to(root).parts
                except ValueError:
                    parts = f.parts
                if not any(part in EXCLUDE_DIRS for part in parts):
                    result["test_files"].append(str(f))
            for f in tests_dir.rglob("test_*.php"):
                try:
                    parts = f.relative_to(root).parts
                except ValueError:
                    parts = f.parts
                if not any(part in EXCLUDE_DIRS for part in parts):
                    result["test_files"].append(str(f))

    result["test_count"] = len(set(result["test_files"]))
    return result


def run_phpunit(root: Path, config_file: str = None, filter_test: str = None, coverage: bool = False) -> dict:
    """Run PHPUnit tests."""
    cmd = [PHPUNIT or PHP, "vendor/bin/phpunit"]
    if config_file:
        cmd.extend(["-c", str(Path(config_file).relative_to(root))])
    if filter_test:
        cmd.extend(["--filter", filter_test])
    if coverage:
        cmd.extend(["--coverage-text"])
    cmd.append("--no-interaction")

    try:
        result = subprocess.run(
            cmd, cwd=str(root), capture_output=True, text=True,
            timeout=300, encoding="utf-8", errors="replace",
        )
        return {
            "framework": "phpunit",
            "exit_code": result.returncode,
            "output": result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout,
            "stderr": result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"framework": "phpunit", "exit_code": -1, "output": "", "stderr": "Test run timed out"}
    except FileNotFoundError:
        return {"framework": "phpunit", "exit_code": -1, "output": "", "stderr": "PHPUnit not found. Run: composer require --dev phpunit/phpunit"}


def run_pest(root: Path, filter_test: str = None) -> dict:
    """Run Pest tests."""
    cmd = [PEST or PHP, "vendor/bin/pest"]
    if filter_test:
        cmd.extend(["--filter", filter_test])
    cmd.append("--no-interaction")

    try:
        result = subprocess.run(
            cmd, cwd=str(root), capture_output=True, text=True,
            timeout=300, encoding="utf-8", errors="replace",
        )
        return {
            "framework": "pest",
            "exit_code": result.returncode,
            "output": result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout,
            "stderr": result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"framework": "pest", "exit_code": -1, "output": "", "stderr": "Test run timed out"}
    except FileNotFoundError:
        return {"framework": "pest", "exit_code": -1, "output": "", "stderr": "Pest not found. Run: composer require --dev pestphp/pest"}


def main():
    parser = argparse.ArgumentParser(description="php_test_runner.py - PHP test discovery & runner")
    parser.add_argument("path", help="PHP project directory")
    parser.add_argument("--filter", metavar="TEST", help="Filter tests by name")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--json", "-j", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Discover tests only, don't run")
    parser.add_argument("--version", action="version", version="php_test_runner.py v1.0.0")

    args = parser.parse_args()
    root = Path(args.path)
    if not root.exists():
        print(f"Not found", file=sys.stderr); sys.exit(1)

    if not root.is_dir():
        root = root.parent

    print(f"\n🧪 PHP Test Runner v1.0.0 — {root}")
    print(f"{'=' * 70}")

    tests = discover_test_files(root)
    print(f"   Framework: {tests['framework'].upper()}")
    print(f"   Config: {tests['config_file'] or 'None found'}")
    print(f"   Test files: {tests['test_count']}")

    if tests["test_count"] > 0 and not args.dry_run:
        print(f"\n   Test files:")
        for tf in sorted(set(tests["test_files"]))[:15]:
            print(f"     - {Path(tf).relative_to(root)}")
        if tests["test_count"] > 15:
            print(f"     ... and {tests['test_count'] - 15} more")

    if args.dry_run:
        if args.json:
            print(json.dumps(tests, indent=2, ensure_ascii=False))
        return

    # Run
    if not PHP:
        print("\n   ❌ PHP not found in PATH")
        sys.exit(1)

    print(f"\n   Running tests...")
    print(f"{'=' * 70}\n")

    if tests["framework"] == "phpunit" and tests["test_count"] > 0:
        result = run_phpunit(root, tests["config_file"], args.filter, args.coverage)
    elif tests["framework"] == "pest":
        result = run_pest(root, args.filter)
    else:
        print("   No test framework detected. Create phpunit.xml or install PHPUnit/Pest.")
        sys.exit(0)

    print(result["output"])
    if result["stderr"]:
        print(f"\n   [STDERR]\n{result['stderr']}")

    status = "✅ PASSED" if result["exit_code"] == 0 else "❌ FAILED" if result["exit_code"] > 0 else "⚠ ERROR"
    print(f"\n{'=' * 70}")
    print(f"   {status} (exit code: {result['exit_code']})")

    if args.json:
        output = {**tests, "result": result}
        print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
