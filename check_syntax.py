#!/usr/bin/env python3
"""Syntax check all Python files using AST (no .pyc written)."""
__maker__ = "SmokerGreenOG"
import _protect
import ast
import sys
from pathlib import Path

# Directories and file patterns to skip
SKIP_DIRS = {"__pycache__", ".rsi_backups", ".rsi_reports",
             ".self_improve_reports", ".backups", ".git",
             ".venv", "venv", "node_modules", "build", "dist"}
SKIP_NAMES = {
    "codex_audit_report.md", "codex_audit_report.html",
}

errors = 0
scanned = 0
skipped = 0

for p in Path('.').rglob('*.py'):
    # Skip excluded directories
    parts = set(p.parts)
    if parts & SKIP_DIRS:
        skipped += 1
        continue

    # Skip generated report files (even if they have .py extension)
    if p.name.lower() in SKIP_NAMES:
        skipped += 1
        continue

    if any(part.startswith('.rsi_') for part in p.parts):
        skipped += 1
        continue

    try:
        ast.parse(p.read_text(encoding='utf-8'), filename=str(p))
        scanned += 1
    except SyntaxError as e:
        print(f'FAIL: {p}: {e}', file=sys.stderr)
        errors += 1

if errors:
    print(f'{errors} file(s) have syntax errors', file=sys.stderr)
    sys.exit(1)

print(f'All {scanned} scanned Python file(s) have valid syntax '
      f'({skipped} skipped)')
