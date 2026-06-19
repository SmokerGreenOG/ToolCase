#!/usr/bin/env python3
"""
dependency_visualizer.py — Genereert Mermaid.js dependency diagrams.

Output:
  - Mermaid grafiek (plakbaar in Markdown/README)
  - Circular dependency detectie
  - Per-module grouping
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import ast
import json
import sys
from pathlib import Path
from collections import defaultdict

EXCLUDE_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".backups", ".rsi_reports", ".rsi_backups", "release",
    "build", "dist",
})


def extract_imports(filepath: Path) -> list[str]:
    """Extract imported module names from a Python file."""
    modules = []
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return modules

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module.split(".")[0])
    return modules


def build_graph(workspace: Path) -> dict:
    """Build import graph: {file -> [imported files]}."""
    graph = defaultdict(set)
    all_files = {}
    py_files = list(workspace.glob("*.py"))

    # Map module name -> file
    for fp in py_files:
        if fp.name.startswith("_") or fp.name.startswith("test_"):
            continue
        mod_name = fp.stem
        all_files[mod_name] = fp.name

    # Build import edges
    for fp in py_files:
        if fp.name.startswith("_") or fp.name.startswith("test_"):
            continue
        source = fp.stem
        imports = extract_imports(fp)
        for imp in imports:
            if imp in all_files and imp != source:
                graph[source].add(imp)

    return {"graph": {k: sorted(v) for k, v in graph.items()},
            "files": all_files}


def find_circular(graph: dict[str, set[str]]) -> list[list[str]]:
    """Find circular dependencies using DFS."""
    cycles = []
    visited = set()
    stack = set()

    def dfs(node: str, path: list[str]) -> None:
        if node in stack:
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            if cycle not in cycles and cycle[::-1] not in cycles:
                cycles.append(cycle)
            return
        if node in visited:
            return
        visited.add(node)
        stack.add(node)
        for neighbor in graph.get(node, []):
            dfs(neighbor, path + [node])
        stack.discard(node)

    for node in graph:
        dfs(node, [])

    return cycles


def generate_mermaid(graph: dict[str, set[str]]) -> str:
    """Generate Mermaid.js diagram."""
    lines = ["```mermaid", "graph TD"]
    seen = set()

    for source, targets in sorted(graph.items()):
        src_id = source.replace("-", "_").replace(".", "_")
        if not targets:
            lines.append(f"    {src_id}({source})")
        for tgt in sorted(targets):
            tgt_id = tgt.replace("-", "_").replace(".", "_")
            key = (source, tgt)
            if key not in seen:
                seen.add(key)
                lines.append(f"    {src_id} --> {tgt_id}")

    lines.append("```")
    return "\n".join(lines)


def print_report(data: dict) -> None:
    """Print formatted report."""
    graph = data["graph"]
    files = data["files"]
    edges = sum(len(v) for v in graph.values())
    nodes = len(graph)
    cycles = find_circular(graph)

    print()
    print("=" * 60)
    print(" 🔗 DEPENDENCY VISUALIZER")
    print("=" * 60)
    print(f"   Nodes: {nodes}  |  Edges: {edges}")
    print(f"   Circular deps: {len(cycles)}")

    # Circular deps
    if cycles:
        print()
        print(f"   ⚠️  CIRCULAR DEPENDENCIES:")
        for i, cycle in enumerate(cycles, 1):
            arrow = " → ".join(cycle)
            print(f"   {i}. {arrow}")

    # Top importers
    print()
    print(f"   TOP IMPORTED:")
    imported_count = defaultdict(int)
    for source, targets in graph.items():
        for tgt in targets:
            imported_count[tgt] += 1
    for mod, count in sorted(imported_count.items(), key=lambda x: -x[1])[:10]:
        print(f"   {count:3d}x  ← {mod}")

    # Mermaid
    print()
    print(f"   {'─'*56}")
    print(f"   MERMAID DIAGRAM (plak in README.md):")
    print(f"   {'─'*56}")
    print()
    print(generate_mermaid(graph))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dependency Visualizer — Mermaid.js diagrams"
    )
    parser.add_argument("path", nargs="?", default=".", help="Workspace")
    parser.add_argument("--json", "-j", action="store_true")
    parser.add_argument("--mermaid-only", "-m", action="store_true",
                        help="Alleen Mermaid output")
    parser.add_argument("--version", action="version", version="1.0.0")

    args = parser.parse_args()
    target = Path(args.path).resolve()

    if not target.exists():
        print(f"❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    data = build_graph(target)
    graph = data["graph"]
    cycles = find_circular(graph)

    if args.mermaid_only:
        print(generate_mermaid(graph))
    elif args.json:
        print(json.dumps({
            "nodes": len(graph),
            "edges": sum(len(v) for v in graph.values()),
            "circular": len(cycles),
            "cycles": cycles,
            "graph": graph,
        }, indent=2))
    else:
        print_report(data)


if __name__ == "__main__":
    main()
