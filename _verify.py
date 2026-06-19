#!/usr/bin/env python3
"""Verify all ToolCase v3.0 files compile."""
import ast
from pathlib import Path

BASE = Path(r"D:\HermesWorkspace\Brain\ToolCase v3.0")
FILES = [
    "error_explainer.py",
    "release_packager.py",
    "skill_installer.py",
    "log_viewer.py",
    "build_doctor.py",
    "state_inspector.py",
    "i18n.py",
    "docs_sync.py",
    "file_guard.py",
]

ok = 0
fail = 0
for fname in FILES:
    fpath = BASE / fname
    try:
        ast.parse(fpath.read_text(encoding="utf-8"))
        print(f"✅ {fname}")
        ok += 1
    except SyntaxError as e:
        print(f"❌ {fname}: {e}")
        fail += 1

print(f"\n{ok} passed, {fail} failed")
