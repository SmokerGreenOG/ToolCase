#!/usr/bin/env python3
"""Show detailed info about all long lines."""
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
        continue
    print(f"\n{'='*80}")
    print(f"{fname}: {len(long_lines)} long lines")
    print(f"{'='*80}")
    for num, text in long_lines:
        # Show first 120 chars
        print(f"\nL{num} (len={len(text)}):")
        print(f"  {text[:120]}")
        if len(text) > 120:
            print(f"  ...{text[-60:]}")
