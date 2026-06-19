#!/usr/bin/env python3
"""List all lines > 100 chars in ToolCase files."""
from pathlib import Path

BASE = Path(r"D:\HermesWorkspace\Brain\ToolCase v3.0")
files = [
    "error_explainer.py", "release_packager.py", "skill_installer.py",
    "log_viewer.py", "build_doctor.py", "state_inspector.py",
    "i18n.py", "docs_sync.py", "file_guard.py"
]

for fname in files:
    fpath = BASE / fname
    lines = fpath.read_text(encoding="utf-8").splitlines()
    long_lines = [(i+1, l) for i, l in enumerate(lines) if len(l) > 100]
    if not long_lines:
        print(f"{fname}: No long lines")
        continue
    print(f"\n{'='*60}")
    print(f"{fname}: {len(long_lines)} line(s) > 100 chars")
    print(f"{'='*60}")
    for num, text in long_lines:
        print(f"  L{num}: len={len(text)}")
