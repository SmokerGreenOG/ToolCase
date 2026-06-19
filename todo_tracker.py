#!/usr/bin/env python3
"""
todo_tracker.py — Scan project for TODO, FIXME, HACK, XXX and track them.

Features:
  - Find all TODO/FIXME/HACK/XXX/BUG/OPTIMIZE/NOTE/TEMP markers
  - Extract descriptions, assignees (@user), priorities (! / !! / !!!)
  - Line/file counts per category
  - Summary statistics
  - JSON output for CI/CD integration

Gebruik:
    python todo_tracker.py <path>
    python todo_tracker.py <path> --json
    python todo_tracker.py <path> --assignees
    python todo_tracker.py <path> --priority-only
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import os
import re
import sys
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = frozenset({
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    ".tox", ".eggs", "build", "dist", ".next",
})

EXCLUDE_EXTENSIONS = frozenset({
    ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".mp4", ".ogg", ".wav",
    ".zip", ".tar", ".gz", ".bz2", ".7z",
    ".lock", ".sum",
})

# Marker detection patterns — only matches in comments (#) or docstrings (""")
TODO_PATTERN = re.compile(
    r'(?:#|\"\"\").*?((?:TODO|FIXME|HACK|XXX|BUG|OPTIMIZE|OPTIMISE|NOTE|TEMP|WORKAROUND|KLUDGE|HARCODED))'
    r'(?:\s*[\(\[#]\s*(\w[\w.@+-]*)\s*[\)\]]?)?'  # Optional assignee
    r'(?:\s*[:;]\s*)?'  # Optional separator
    r'([^\n]*)',  # Description
    re.IGNORECASE
)

# Priority detection
PRIORITY_PATTERN = re.compile(r'(?<!!)!+')

CATEGORIES = {
    "TODO": "todo",
    "FIXME": "fixme",
    "HACK": "hack",
    "XXX": "xxx",
    "BUG": "bug",
    "OPTIMIZE": "optimize",
    "OPTIMISE": "optimize",
    "NOTE": "note",
    "TEMP": "temp",
    "WORKAROUND": "workaround",
    "KLUDGE": "kludge",
    "HARCODED": "harcoded",
}

PRIORITY_MAP = {
    "!!!": "HIGH",
    "!!": "MEDIUM",
    "!": "LOW",
}

CATEGORY_ICONS = {
    "todo": "📝",
    "fixme": "🔧",
    "hack": "🤯",
    "xxx": "⚠️",
    "bug": "🐛",
    "optimize": "⚡",
    "note": "💡",
    "temp": "⏳",
    "workaround": "🩹",
    "kludge": "🛠",
    "harcoded": "🔴",
}


def collect_files(root: Path) -> list[Path]:
    """Collect all text source files."""
    files = []

    if root.is_file():
        return [root]

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            fp = Path(dirpath) / fn
            ext = fp.suffix.lower()
            if ext not in EXCLUDE_EXTENSIONS:
                # Skip binary files by trying to read as text
                try:
                    with open(fp, "rb") as f:
                        chunk = f.read(1024)
                        if b"\x00" in chunk:
                            continue  # Binary
                except Exception:
                    continue
                files.append(fp)

    return sorted(files)


def scan_file(filepath: Path, base_path: Path = None) -> list[dict]:
    """Scan a single file for TODO/FIXME markers."""
    todos = []

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return todos

    lines = content.split("\n")

    for i, line in enumerate(lines, 1):
        for match in TODO_PATTERN.finditer(line):
            marker = match.group(1).upper()
            assignee = match.group(2)
            description = match.group(3).strip() if match.group(3) else ""

            # Detect priority
            priority = "NONE"
            prio_match = PRIORITY_PATTERN.search(description)
            if prio_match:
                p = prio_match.group()
                priority = PRIORITY_MAP.get(p, "MEDIUM")
                # Remove the ! marks from description
                description = PRIORITY_PATTERN.sub("", description).strip()

            category = CATEGORIES.get(marker, "todo")
            try:
                file_rel = filepath.relative_to(base_path) if base_path else filepath.relative_to(Path.cwd())
            except ValueError:
                file_rel = filepath

            todos.append({
                "file": str(filepath),
                "file_rel": str(file_rel),
                "line": i,
                "marker": marker,
                "category": category,
                "assignee": assignee,
                "description": description,
                "priority": priority,
                "context": line.strip()[:120],
            })

    return todos


def print_report(all_todos: list[dict], show_assignees: bool = False,
                 priority_only: str = None) -> None:
    """Print a formatted TODO report."""
    if not all_todos:
        print("\n ✅ Geen TODO/FIXME/HACK markers gevonden!")
        return

    # Filter by priority if requested
    if priority_only:
        all_todos = [t for t in all_todos if t["priority"] == priority_only.upper()]

    # Count by category
    by_category = defaultdict(list)
    for t in all_todos:
        by_category[t["category"]].append(t)

    # Count priorities
    priorities = Counter(t["priority"] for t in all_todos)

    # Count assignees
    assignees = Counter(t["assignee"] for t in all_todos if t["assignee"])

    total = len(all_todos)

    print(f"\n{'='*60}")
    print(f" 📋 TODO TRACKER — {total} marker(s)")
    print(f"{'='*60}")
    print(f"   🔴 HIGH priority:   {priorities.get('HIGH', 0)}")
    print(f"   🟡 MEDIUM priority: {priorities.get('MEDIUM', 0)}")
    print(f"   🟢 LOW priority:    {priorities.get('LOW', 0)}")
    print(f"   ⚪ No priority:     {priorities.get('NONE', 0)}")
    print()

    if show_assignees and assignees:
        print(f" ── Toegewezen aan ({len(assignees)}) ──")
        for assignee, count in assignees.most_common(10):
            print(f"   👤 @{assignee}: {count}x")
        print()

    # Per-category report
    categories = ["fixme", "bug", "hack", "todo", "optimize",
                   "temp", "workaround", "note", "xxx",
                   "kludge", "harcoded"]
    for category in categories:
        items = by_category.get(category, [])
        if not items:
            continue

        icon = CATEGORY_ICONS.get(category, "📌")
        label = category.upper()
        print(f" ── {icon} {label} ({len(items)}) ──")

        # Sort by priority first
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3}
        items.sort(key=lambda x: (priority_order.get(x["priority"], 99), x["file"], x["line"]))

        for item in items[:20]:
            prio_tag = f"[{item['priority']}] " if item['priority'] != "NONE" else ""
            assignee_tag = f"(@{item['assignee']}) " if item['assignee'] else ""
            desc = item["description"][:60] if item["description"] else "(geen beschrijving)"
            print(f"   {prio_tag}{assignee_tag}{item['file_rel']}:{item['line']} — {desc}")
        if len(items) > 20:
            print(f"   ... en nog {len(items) - 20} meer")
        print()

    # Summary by file
    by_file = Counter(t["file_rel"] for t in all_todos)
    print(f" ── Per Bestand ──")
    for filepath, count in by_file.most_common(10):
        print(f"   📄 {filepath}: {count} marker(s)")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="todo_tracker.py — Scan project for TODO/FIXME/HACK markers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python todo_tracker.py .
  python todo_tracker.py src/ --json
  python todo_tracker.py . --assignees
  python todo_tracker.py . --priority-only high
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Bestand of directory")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--assignees", "-a", action="store_true",
                        help="Toon toegewezen personen")
    parser.add_argument("--priority-only", "-p",
                        choices=["high", "medium", "low"],
                        help="Filter op priority")
    parser.add_argument("--version", action="version", version="todo_tracker.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 TODO Tracker v1.0.0 — scanning {target}")

    files = collect_files(target)
    if not files:
        print(" Geen bestanden om te scannen")
        sys.exit(0)

    print(f"   {len(files)} bestand(en) om te scannen")

    all_todos = []
    for fp in files:
        todos = scan_file(fp, target)
        all_todos.extend(todos)

    if args.json:
        stats = {
            "total": len(all_todos),
            "by_category": dict(Counter(t["category"] for t in all_todos)),
            "by_priority": dict(Counter(t["priority"] for t in all_todos)),
            "by_file": dict(Counter(str(Path(t["file_rel"])) for t in all_todos)),
            "todos": all_todos,
            "scanned_at": datetime.now().isoformat(),
        }
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    else:
        print_report(all_todos, args.assignees, args.priority_only)


if __name__ == "__main__":
    main()
