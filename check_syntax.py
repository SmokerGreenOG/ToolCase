#!/usr/bin/env python3
"""Syntax check all Python files using AST (no .pyc written)."""
__maker__ = "SmokerGreenOG"
import _protect
import ast
import sys
from pathlib import Path

errors = 0
for p in Path('.').rglob('*.py'):
    if '__pycache__' in str(p) or '.rsi_' in str(p):
        continue
    try:
        ast.parse(p.read_text(encoding='utf-8'), filename=str(p))
    except SyntaxError as e:
        print(f'FAIL: {p}: {e}', file=sys.stderr)
        errors += 1

if errors:
    print(f'{errors} file(s) have syntax errors', file=sys.stderr)
    sys.exit(1)

print('All Python files have valid syntax')
