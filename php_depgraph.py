#!/usr/bin/env python3
"""
php_depgraph.py — PHP dependency graph analyzer.

Analyseert PHP projecten op:
  - include/require/include_once/require_once dependencies
  - Namespace imports (use statements) en class references
  - Circular dependency detection
  - Per-file import/export overzicht

Gebruik:
    python php_depgraph.py <path> --recursive
    python php_depgraph.py <path> --json
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

EXCLUDE_DIRS = {"node_modules", "vendor", ".git", "__pycache__", "tests/fixtures", ".venv", "venv", "dist", "build", ".cache"}

INCLUDE_PATTERN = re.compile(
    r'(?:include|require|include_once|require_once)\s*(?:\(?\s*)?'
    r'(?:__DIR__\s*\.\s*)?[\"\']([^\"\']+\.php)[\"\']',
)
NAMESPACE_PATTERN = re.compile(r'^\s*namespace\s+([\w\\]+)\s*;', re.MULTILINE)
USE_PATTERN = re.compile(r'^\s*use\s+([\w\\]+)(?:\s+as\s+(\w+))?\s*;', re.MULTILINE)
CLASS_PATTERN = re.compile(r'^\s*(?:abstract\s+)?(?:final\s+)?class\s+(\w+)', re.MULTILINE)


def discover_php_files(root: Path) -> list[Path]:
    """discover php files.
    
        Args:
            root: Description.
    
        Returns:
            Description.
        """
    files = []
    for f in root.rglob("*.php"):
        try:
            parts = f.relative_to(root).parts
        except ValueError:
            parts = f.parts
        if any(part in EXCLUDE_DIRS for part in parts):
            continue
        files.append(f)
    return sorted(set(files))


def analyze_file(filepath: Path, root: Path) -> dict:
    """Analyze a single PHP file for includes/requires and namespaces."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return {"file": str(filepath), "includes": [], "namespace": None, "uses": [], "classes": []}

    rel = str(filepath.relative_to(root)) if filepath.is_relative_to(root) else filepath.name

    # Includes
    includes = []
    for m in INCLUDE_PATTERN.finditer(source):
        includes.append({"path": m.group(1), "line": source[:m.start()].count('\n') + 1})

    # Namespace
    ns_match = NAMESPACE_PATTERN.search(source)
    namespace = ns_match.group(1) if ns_match else None

    # Use statements
    uses = []
    for m in USE_PATTERN.finditer(source):
        uses.append({"fqcn": m.group(1), "alias": m.group(2) or m.group(1).split('\\')[-1]})

    # Classes
    classes = CLASS_PATTERN.findall(source)

    return {
        "file": rel,
        "includes": includes,
        "namespace": namespace,
        "uses": uses,
        "classes": classes,
        "included_by": [],
    }


def detect_circular(graph: dict) -> list[list[str]]:
    """DFS-based circular dependency detection."""
    visited = set()
    stack = []
    cycles = []

    def dfs(node: str, path: list[str]) -> None:
        """Depth-first traversal for cycle detection."""
        visited.add(node)
        stack.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if dfs(neighbor, path + [neighbor]):
                    return True
            elif neighbor in stack:
                cycle_start = stack.index(neighbor)
                cycles.append(stack[cycle_start:] + [neighbor])
                return True
        stack.pop()
        return False

    for node in list(graph.keys()):
        if node not in visited:
            dfs(node, [node])

    return cycles


def print_report(results: list[dict], cycles: list[list[str]]) -> None:
    """Print a human-readable dependency graph report."""
    total_includes = sum(len(r["includes"]) for r in results)

    for r in results:
        status = "🔴" if r["file"] in [c[0] for c in cycles] else "✅"
        print(f"\n{'=' * 70}")
        print(f" {status} {r['file']}")
        print(f"{'=' * 70}")

        if r["namespace"]:
            print(f"   Namespace: {r['namespace']}")
        if r["classes"]:
            print(f"   Classes: {', '.join(r['classes'])}")
        if r["uses"]:
            print(f"   Uses ({len(r['uses'])}):")
            for u in r["uses"]:
                print(f"     - {u['fqcn']} as {u['alias']}")
        if r["includes"]:
            print(f"   Includes ({len(r['includes'])}):")
            for inc in r["includes"]:
                print(f"     - {inc['path']} (line {inc['line']})")
        if r["included_by"]:
            print(f"   Included by ({len(r['included_by'])}):")
            for ib in r["included_by"]:
                print(f"     - {ib}")

    print(f"\n{'=' * 70}")
    print(f" DEPENDENCY SUMMARY")
    print(f"{'=' * 70}")
    print(f"   Files:        {len(results)}")
    print(f"   Total includes: {total_includes}")

    if cycles:
        print(f"\n   ⚠ CIRCULAR DEPENDENCIES ({len(cycles)}):")
        for i, cycle in enumerate(cycles, 1):
            print(f"     Cycle {i}: {' → '.join(cycle)}")
    else:
        print(f"   ✅ No circular dependencies")

    print()


def print_json(results: list[dict], cycles: list[list[str]]) -> None:
    """Print a machine-readable JSON dependency report."""
    output = {
        "summary": {
            "total_files": len(results),
            "total_includes": sum(len(r["includes"]) for r in results),
            "circular_dependencies": len(cycles),
        },
        "cycles": [" → ".join(c) for c in cycles],
        "files": results,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


def main():
    """main.
        """
    parser = argparse.ArgumentParser(description="php_depgraph.py - PHP dependency graph")
    parser.add_argument("path", help="PHP file or directory")
    parser.add_argument("--recursive", "-r", action="store_true", help="Recursive scan")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--version", action="version", version="php_depgraph.py v1.0.0")

    args = parser.parse_args()
    target = Path(args.path)
    if not target.exists():
        print(f"'{args.path}' not found", file=sys.stderr); sys.exit(1)

    root = target if target.is_dir() else target.parent
    files = [target] if target.is_file() else (discover_php_files(target) if args.recursive else sorted(target.glob("*.php")))

    if not files:
        print("No PHP files found"); sys.exit(0)

    print(f"\n🔗 PHP DepGraph v1.0.0 — {len(files)} file(s)")
    print(f"{'=' * 70}")

    results = [analyze_file(f, root) for f in files]

    # Build dependency graph
    file_map = {r["file"]: r for r in results}
    graph = defaultdict(list)
    for r in results:
        for inc in r["includes"]:
            graph[r["file"]].append(inc["path"])
            # Mark included_by
            if inc["path"] in file_map:
                file_map[inc["path"]]["included_by"].append(r["file"])

    cycles = detect_circular(dict(graph))

    if args.json:
        print_json(results, cycles)
    else:
        print_report(results, cycles)


if __name__ == "__main__":
    main()
