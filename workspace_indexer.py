#!/usr/bin/env python3
"""
workspace_indexer.py — Index project workspace for fast file search and navigation.

Features:
  - Build a searchable index of all project files
  - Detect file types, sizes, last modified dates
  - Show directory tree with file count stats
  - Find duplicate filenames
  - Generate workspace summary report
  - Export index as JSON for external tools

Gebruik:
    python workspace_indexer.py <path>                # Index + report
    python workspace_indexer.py <path> --json          # JSON output
    python workspace_indexer.py <path> --tree          # ASCII tree
    python workspace_indexer.py <path> --duplicates    # Find duplicate filenames
    python workspace_indexer.py <path> --search *.py   # Search by glob
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

EXCLUDE_DIRS = frozenset(
    {
        "node_modules",
        "target",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".eggs",
        "build",
        "dist",
        ".next",
        ".husky/_",
        ".git2",
        ".svn",
        ".hg",
        ".backups",
        ".rsi_backups",
        ".rsi_reports",
        ".self_improve_reports",
    }
)

EXCLUDE_EXTENSIONS = frozenset(
    {
        ".pyc",
        ".pyo",
        ".so",
        ".dll",
        ".dylib",
        ".exe",
        ".lock",
        ".sum",
    }
)

ICON_MAP = {
    ".py": "🐍",
    ".ts": "🔷",
    ".tsx": "⚛️",
    ".js": "🟨",
    ".jsx": "⚛️",
    ".rs": "🦀",
    ".html": "🌐",
    ".css": "🎨",
    ".scss": "🎨",
    ".json": "📋",
    ".yaml": "📋",
    ".yml": "📋",
    ".toml": "📋",
    ".md": "📝",
    ".txt": "📄",
    ".env": "🔒",
    ".gitignore": "🙈",
    ".sh": "💻",
    ".bat": "💻",
    ".ps1": "💻",
}

LANG_MAP = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript React",
    ".js": "JavaScript",
    ".jsx": "JavaScript React",
    ".rs": "Rust",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".md": "Markdown",
    ".sh": "Shell",
    ".bat": "Batch",
    ".ps1": "PowerShell",
}


def index_workspace(root: Path) -> dict:
    """Build a complete workspace index."""
    index = {
        "root": str(root),
        "total_files": 0,
        "total_dirs": 0,
        "total_size": 0,
        "files": [],
        "dirs": [],
        "by_extension": defaultdict(int),
        "by_language": defaultdict(int),
        "by_size_range": defaultdict(int),
        "duplicates": [],
    }

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        path = Path(dirpath)

        index["total_dirs"] += 1
        rel_dir = path.relative_to(root)
        index["dirs"].append(
            {
                "path": str(rel_dir),
                "files": len(filenames),
            }
        )

        for fn in filenames:
            ext = Path(fn).suffix.lower()
            if ext in EXCLUDE_EXTENSIONS:
                continue

            fp = path / fn
            try:
                stat = fp.stat()
            except Exception:
                continue

            rel_path = fp.relative_to(root)
            lang = LANG_MAP.get(ext, "Other")

            file_info = {
                "path": str(rel_path),
                "name": fn,
                "ext": ext,
                "language": lang,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }

            index["total_files"] += 1
            index["total_size"] += stat.st_size
            index["files"].append(file_info)
            index["by_extension"][ext or "(no ext)"] += 1
            index["by_language"][lang] += 1

            # Size ranges
            if stat.st_size < 1024:
                index["by_size_range"]["<1 KB"] += 1
            elif stat.st_size < 10240:
                index["by_size_range"]["1-10 KB"] += 1
            elif stat.st_size < 102400:
                index["by_size_range"]["10-100 KB"] += 1
            elif stat.st_size < 1048576:
                index["by_size_range"]["100 KB-1 MB"] += 1
            else:
                index["by_size_range"][">1 MB"] += 1

    # Find duplicates (same filename in different dirs)
    name_map = defaultdict(list)
    for f in index["files"]:
        name_map[f["name"]].append(f["path"])
    index["duplicates"] = [
        {"name": name, "paths": paths} for name, paths in name_map.items() if len(paths) > 1
    ]

    return index


def find_by_glob(index: dict, pattern: str) -> list[dict]:
    """Find files matching a glob pattern in the index."""
    # Convert simple glob to regex
    regex = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
    compiled = re.compile(f"^{regex}$", re.IGNORECASE)

    results = []
    for f in index["files"]:
        if compiled.match(f["name"]) or compiled.match(f["path"]):
            results.append(f)
    return results


def print_tree(index: dict, max_depth: int = 3) -> None:
    """Print an ASCII directory tree."""
    root = index["root"]
    print(f"\n{'=' * 60}")
    print(f" 📁 WORKSPACE TREE — {root}")
    print(f"{'=' * 60}")

    # Build tree structure
    tree = defaultdict(lambda: {"files": [], "dirs": set()})
    for f in index["files"]:
        parts = Path(f["path"]).parts
        for i in range(len(parts)):
            prefix = os.path.join(*parts[:i]) if i > 0 else ""
            if i < len(parts) - 1:
                tree[prefix]["dirs"].add(parts[i])
            else:
                tree[prefix]["files"].append(f)

    def print_node(prefix: str, depth: int, indent: str = "") -> None:
        """Recursively print a directory tree node up to max_depth."""
        if depth > max_depth:
            return

        node = tree.get(prefix, {"files": [], "dirs": set()})

        if prefix:
            dir_name = os.path.basename(prefix) if prefix else "."
            file_count = len(node["files"])
            child_dirs = sorted(node["dirs"])
            print(f"{indent}📁 {dir_name}/  ({file_count} files, {len(child_dirs)} dirs)")

        # Files in this directory
        if prefix == "":
            # Root level
            for f in sorted(index["files"], key=lambda x: x["path"]):
                if "/" not in f["path"]:
                    icon = ICON_MAP.get(f["ext"], "📄")
                    size_str = _format_size(f["size"])
                    print(f"{indent}  {icon} {f['name']}  ({size_str})")

        child_indent = indent + "  " if prefix else indent
        for child_dir in sorted(node["dirs"]):
            child_prefix = child_dir if not prefix else os.path.join(prefix, child_dir)
            print_node(child_prefix, depth + 1, child_indent)

    print_node("", 0)
    print()


def _format_size(size: int) -> str:
    """Format file size in human-readable format."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"


def print_report(
    index: dict, show_tree: bool = False, duplicates: bool = False, search_pattern: str = None
) -> None:
    """Print a formatted workspace index report."""
    total_size_str = _format_size(index["total_size"])

    print(f"\n{'=' * 60}")
    print(f" 📊 WORKSPACE INDEX — {index['root']}")
    print(f"{'=' * 60}")
    print(f"   📁 Directories: {index['total_dirs']}")
    print(f"   📄 Files:       {index['total_files']}")
    print(f"   💾 Total size:  {total_size_str}")
    print()

    # By language
    print(f" ── Per Taal ──")
    for lang, count in sorted(index["by_language"].items(), key=lambda x: -x[1]):
        print(f"   {lang}: {count} bestand(en)")
    print()

    # By size
    print(f" ── Per Grootte ──")
    for size_range, count in sorted(index["by_size_range"].items()):
        print(f"   {size_range}: {count} bestand(en)")
    print()

    # Top 5 largest files
    largest = sorted(index["files"], key=lambda x: x["size"], reverse=True)[:5]
    print(f" ── Grootste Bestanden ──")
    for f in largest:
        sz = _format_size(f["size"])
        print(f"   📄 {f['path']}  ({sz})")
    print()

    if duplicates:
        dupes = index.get("duplicates", [])
        if dupes:
            print(f" ── Duplicate Filenames ({len(dupes)}) ──")
            for d in dupes[:10]:
                print(f"   🔁 {d['name']}")
                for p in d["paths"]:
                    print(f"      📄 {p}")
            if len(dupes) > 10:
                print(f"   ... en nog {len(dupes) - 10} set(s)")
            print()

    if search_pattern:
        results = find_by_glob(index, search_pattern)
        print(f" ── Search: '{search_pattern}' ({len(results)} resultaten) ──")
        for r in results[:20]:
            icon = ICON_MAP.get(r["ext"], "📄")
            sz = _format_size(r["size"])
            print(f"   {icon} {r['path']}  ({sz})")
        if len(results) > 20:
            print(f"   ... en nog {len(results) - 20} resultaten")
        print()

    if show_tree:
        print_tree(index)


def main() -> None:
    """main."""
    parser = argparse.ArgumentParser(
        description="workspace_indexer.py — Index and analyze project workspace",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python workspace_indexer.py .
  python workspace_indexer.py . --json
  python workspace_indexer.py . --tree
  python workspace_indexer.py . --duplicates
  python workspace_indexer.py . --search *.py
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--tree", "-t", action="store_true", help="ASCII directory tree")
    parser.add_argument("--duplicates", "-d", action="store_true", help="Find duplicate filenames")
    parser.add_argument("--search", "-s", help="Search by glob pattern")
    parser.add_argument("--version", action="version", version="workspace_indexer.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 Workspace Indexer v1.0.0 — indexing {target}")

    index = index_workspace(target)

    if args.json:
        print(json.dumps(index, indent=2, ensure_ascii=False, default=str))
    else:
        print_report(index, args.tree, args.duplicates, args.search)


if __name__ == "__main__":
    main()
