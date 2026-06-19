#!/usr/bin/env python3
"""Verify Python files compile."""
import ast
from pathlib import Path

BASE = Path(r"D:\HermesWorkspace\Brain\ToolCase v3.0")
files = [
    "error_explainer.py", "release_packager.py", "skill_installer.py",
    "log_viewer.py", "build_doctor.py", "state_inspector.py",
    "i18n.py", "docs_sync.py", "file_guard.py"
]
all_ok = True
for fname in files:
    fpath = BASE / fname
    try:
        ast.parse(fpath.read_text(encoding="utf-8"))
        print(f"✅ {fname}")
    except SyntaxError as e:
        print(f"❌ {fname}: {e}")
        all_ok = False
if all_ok:
    print("\nAll files compile OK!")
else:
    print("\nSome files have syntax errors!")
