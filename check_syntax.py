#!/usr/bin/env python3
"""Syntax check all Python files using AST (no .pyc written).

Checks every .py file in the current directory tree for valid Python syntax
using ast.parse(). Excludes generated files, cache dirs, and RSI internals.

Exit codes: 0 = all OK, 1 = syntax errors found.

Usage:
    python check_syntax.py              # Standard output
    python check_syntax.py --json       # JSON output
    python check_syntax.py --help       # Show help
"""
__maker__ = "SmokerGreenOG"
import _protect
import argparse
import ast
import json
import sys
from pathlib import Path

# Directories and file patterns to skip
SKIP_DIRS = {"__pycache__", ".rsi_backups", ".rsi_reports",
             ".self_improve_reports", ".backups", ".git",
             ".venv", "venv", "node_modules", "build", "dist"}
SKIP_NAMES = {
    "codex_audit_report.md", "codex_audit_report.html",
}


def check_syntax(root: Path = None) -> dict:
    """Scan all .py files under root for syntax errors.

    Returns a dict with scanned, skipped, errors count and error details.
    """
    if root is None:
        root = Path('.')
    errors_list = []
    scanned = 0
    skipped = 0

    for p in root.rglob('*.py'):
        # Skip excluded directories
        parts = set(p.parts)
        if parts & SKIP_DIRS:
            skipped += 1
            continue

        # Skip generated report files
        if p.name.lower() in SKIP_NAMES:
            skipped += 1
            continue

        if any(part.startswith('.rsi_') for part in p.parts):
            skipped += 1
            continue

        try:
            source = p.read_text(encoding='utf-8')
            ast.parse(source, filename=str(p))
            # Use compile() to catch from __future__ placement errors
            # that ast.parse() silently accepts
            compile(source, str(p), 'exec')
            scanned += 1
        except SyntaxError as e:
            errors_list.append({
                "file": str(p),
                "line": e.lineno,
                "msg": e.msg,
            })

    return {
        "scanned": scanned,
        "skipped": skipped,
        "errors": len(errors_list),
        "error_details": errors_list,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check Python syntax using AST (no .pyc files written).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON.",
    )
    parser.add_argument(
        "path", nargs="?", default=".",
        help="Directory to scan (default: current directory).",
    )
    args = parser.parse_args()

    result = check_syntax(Path(args.path))

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["errors"]:
            for e in result["error_details"]:
                print(
                    f'FAIL: {e["file"]}: line {e["line"]}: {e["msg"]}',
                    file=sys.stderr,
                )
            print(
                f'{result["errors"]} file(s) have syntax errors',
                file=sys.stderr,
            )
        print(
            f'All {result["scanned"]} scanned Python file(s) '
            f'have valid syntax ({result["skipped"]} skipped)'
        )

    sys.exit(1 if result["errors"] else 0)


if __name__ == "__main__":
    main()
