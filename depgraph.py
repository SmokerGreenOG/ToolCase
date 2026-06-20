#!/usr/bin/env python3
"""
depgraph.py — Import/export dependency graph tool.

Usage:
    python depgraph.py <path>
    python depgraph.py <path> --depth 2
    python depgraph.py <path> --json
    python depgraph.py <path> --external
    python depgraph.py <path> --cycles

Parses Python, TypeScript, and Rust source files to build a dependency
graph. Supports depth-limited tree rendering, JSON output, external
dependency listing, and circular dependency (cycle) detection.
"""
from __future__ import annotations

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = frozenset({"node_modules", "target", ".git", "__pycache__",
        ".backups",
        
        ".rsi_backups",
        
        ".rsi_reports",
        
        ".self_improve_reports",
        })
DEFAULT_MAX_DEPTH = 3

# Regex patterns per language
PYTHON_IMPORT_RE = re.compile(
    r'^\s*(?:from\s+([\w.]+)\s+)?import\s+(.+)$', re.MULTILINE
)
TS_IMPORT_RE = re.compile(
    r"""import\s+(?:(?:type\s+)?\{[^}]*\}\s+from\s+["']([^"']+)["']"""
    r"""|(?:\w+(?:\s*,\s*\{[^}]*\})?)\s+from\s+["']([^"']+)["']"""
    r"""|["']([^"']+)["'])""",
    re.MULTILINE,
)
RUST_USE_RE = re.compile(
    r'^\s*use\s+(.+?)\s*(?:::\{|;|as\s+|$)', re.MULTILINE
)
RUST_MOD_RE = re.compile(r'^\s*mod\s+(\w+)\s*(?:;|\{)', re.MULTILINE)

# Language detection by file extension
EXT_MAP = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "typescript",
    ".jsx": "typescript",
    ".mjs": "typescript",
    ".rs": "rust",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_file(path: Path) -> str:
    """Read a file as text, returning empty string on error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _is_excluded(path: Path, root: Path) -> bool:
    """Check if a path resides inside an excluded directory."""
    try:
        rel = path.relative_to(root)
        for part in rel.parts:
            if part in EXCLUDE_DIRS:
                return True
    except ValueError:
        pass
    return False


def _normalise_module_name(name: str) -> str:
    """Strip whitespace and trailing comments from a module name."""
    return name.split("#")[0].strip()


def _is_external_import(module: str, project_files: set) -> bool:
    """
    Heuristic: if the first component of the module path matches a known
    project file or directory, it's internal; otherwise external.
    """
    first = module.split(".")[0].split("/")[0]
    return first not in project_files


# ---------------------------------------------------------------------------
# Language-specific parsers
# ---------------------------------------------------------------------------


def parse_python(content: str, filepath: Path, project_files: set) -> list:
    """Parse Python imports from content."""
    imports = []
    for match in PYTHON_IMPORT_RE.finditer(content):
        from_mod = match.group(1)
        raw_targets = match.group(2)
        if from_mod:
            # from X import Y, Z
            targets = [t.strip().split(" as ")[0].strip()
                       for t in raw_targets.split(",")]
            for t in targets:
                full = f"{from_mod}.{t}" if "." not in t and t else from_mod
                imports.append({
                    "module": _normalise_module_name(full),
                    "source": "python",
                    "external": _is_external_import(
                        _normalise_module_name(from_mod), project_files
                    ),
                })
        else:
            # import X, Y
            targets = [t.strip().split(" as ")[0].strip()
                       for t in raw_targets.split(",")]
            for t in targets:
                if t:
                    imports.append({
                        "module": _normalise_module_name(t),
                        "source": "python",
                        "external": _is_external_import(
                            _normalise_module_name(t), project_files
                        ),
                    })
    return imports


def parse_typescript(content: str, filepath: Path, project_files: set) -> list:
    """Parse TypeScript/JS imports from content."""
    imports = []
    for match in TS_IMPORT_RE.finditer(content):
        module = match.group(1) or match.group(2) or match.group(3)
        if module:
            mod = _normalise_module_name(module)
            # Relative imports are internal
            is_external = not (mod.startswith(".") or mod.startswith("/"))
            imports.append({
                "module": mod,
                "source": "typescript",
                "external": is_external,
            })
    return imports


def parse_rust(content: str, filepath: Path, project_files: set) -> list:
    """Parse Rust use/mod statements from content."""
    imports = []

    # use X::Y::Z;
    for match in RUST_USE_RE.finditer(content):
        raw = match.group(1).strip()
        # Handle `use X::{Y, Z}` — split on `::` up to the brace
        if "::{" in raw:
            base, rest = raw.split("::{", 1)
            items = [i.strip().rstrip("}").strip() for i in rest.split(",")]
            for item in items:
                item = item.strip().rstrip("}").strip()
                if item:
                    full = f"{base}::{item}"
                    imports.append({
                        "module": full,
                        "source": "rust",
                        "external": _is_external_import(
                            base.split("::")[0], project_files
                        ),
                    })
        else:
            # Strip trailing semicolon, `as alias`, `use X::Y`
            mod = raw.rstrip(";").split(" as ")[0].strip()
            if mod:
                imports.append({
                    "module": mod,
                    "source": "rust",
                    "external": _is_external_import(
                        mod.split("::")[0], project_files
                    ),
                })

    # mod X; — crate-level mod declarations
    for match in RUST_MOD_RE.finditer(content):
        mod_name = match.group(1)
        full = f"crate::{mod_name}"
        imports.append({
            "module": full,
            "source": "rust",
            "external": False,
        })

    return imports


# ---------------------------------------------------------------------------
# Parsing dispatcher
# ---------------------------------------------------------------------------

PARSERS = {
    "python": parse_python,
    "typescript": parse_typescript,
    "rust": parse_rust,
}


def parse_file(filepath: Path, root: Path, project_files: set) -> tuple:
    """Parse a single file and return (filepath, lang, [imports])."""
    ext = filepath.suffix.lower()
    lang = EXT_MAP.get(ext)
    if lang is None:
        return filepath, None, []

    content = _read_file(filepath)
    if not content:
        return filepath, lang, []

    parser = PARSERS[lang]
    imports = parser(content, filepath, project_files)
    return filepath, lang, imports


# ---------------------------------------------------------------------------
# Build the full dependency graph
# ---------------------------------------------------------------------------


def build_graph(root: Path, show_external: bool = False) -> tuple[dict, set]:
    """
    Walk *root*, parse every recognised source file, and return:
        graph: dict[filepath -> list[import_dict]]
        project_files: set of first-component names for external detection
    """
    root = Path(root).resolve()
    all_files = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIRS
        ]
        for fn in filenames:
            fp = Path(dirpath) / fn
            ext = fp.suffix.lower()
            if ext in EXT_MAP:
                rel = fp.relative_to(root)
                all_files.append(fp)

    # Build set of first-level names for external detection
    project_names = set()
    for fp in all_files:
        try:
            rel = fp.relative_to(root)
            project_names.add(rel.parts[0].removesuffix(".py")
                              .removesuffix(".rs").removesuffix(".ts")
                              .removesuffix(".tsx").removesuffix(".js")
                              .removesuffix(".jsx").removesuffix(".mjs"))
        except Exception:
            pass
    # Also add top-level directory names
    for d in os.listdir(root):
        if os.path.isdir(root / d) and d not in EXCLUDE_DIRS:
            project_names.add(d)

    graph = {}
    for fp in all_files:
        _, lang, imports = parse_file(fp, root, project_names)
        if lang:
            if not show_external:
                imports = [imp for imp in imports if not imp["external"]]
            graph[str(fp)] = {
                "filepath": str(fp),
                "language": lang,
                "imports": imports,
            }
    return graph, project_names


# ---------------------------------------------------------------------------
# Tree rendering
# ---------------------------------------------------------------------------


def render_tree(
    graph: dict,
    start_path: str,
    depth: int = DEFAULT_MAX_DEPTH,
    seen: set = None,
    _current_depth: int = 0,
) -> list:
    """Render an ASCII dependency tree rooted at *start_path*."""
    if _current_depth > depth:
        return []
    if seen is None:
        seen = set()

    lines = []
    indent = "  " * _current_depth
    prefix = "└─ " if _current_depth > 0 else ""
    node = graph.get(start_path)

    if node is None:
        lines.append(f"{indent}{prefix}{start_path}  [not found in graph]")
        return lines

    label = f"{start_path}  [{node['language']}]"
    if start_path in seen:
        lines.append(f"{indent}{prefix}{label}  [circular ref]")
        return lines

    lines.append(f"{indent}{prefix}{label}")
    seen.add(start_path)

    children = node["imports"]
    if not children:
        lines.append(f"{indent}  └─ (no imports)")
    else:
        for i, imp in enumerate(children):
            is_last = i == len(children) - 1
            imp_prefix = "└─ " if is_last else "├─ "
            mod = imp["module"]
            tag = " [ext]" if imp["external"] else ""
            lines.append(f"{indent}  {imp_prefix}{mod}{tag}")

            # Try to resolve module to a file for recursive traversal
            resolved = _resolve_import(start_path, imp["module"], graph)
            if resolved and resolved in graph and resolved not in seen:
                subtree = render_tree(
                    graph, resolved, depth, seen, _current_depth + 2
                )
                # Adjust prefix for subtree continuation
                for j, subline in enumerate(subtree):
                    if j == 0:
                        # Replace the first line which is the file header
                        # with an inline rendering
                        continue
                    lines.append(subline)

    return lines


def _resolve_import(current_file: str, module: str, graph: dict | None = None) -> str | None:
    """
    Naive resolution of module name to a filepath in the graph.
    Tries common extensions.
    """
    if graph is None:
        return None

    # Relative TS imports: ./foo -> foo.ts, ./dir/mod -> dir/mod.ts
    if module.startswith("."):
        cur_dir = os.path.dirname(current_file)
        candidate = os.path.normpath(os.path.join(cur_dir, module))
    else:
        candidate = module.replace(".", "/")

    # Try with various extensions
    for ext in EXT_MAP:
        for base in [candidate, candidate + "/index", candidate + "/mod"]:
            path = base + ext
            if path in graph:
                return path
            # Also try under 'src' for Rust
            parts = current_file.split(os.sep)
            if "src" in parts:
                src_idx = parts.index("src")
                root_parts = parts[:src_idx]
                alt = os.path.join(*(root_parts + [base.lstrip("/") + ext]))
                if alt in graph:
                    return alt

    return None


# ---------------------------------------------------------------------------
# Cycle detection (DFS-based)
# ---------------------------------------------------------------------------


def find_cycles(graph: dict, show_external: bool = False) -> list:
    """
    Detect circular dependencies using DFS cycle detection.
    Returns a list of (cycle_start, [path_of_files]).
    """
    adj = defaultdict(list)
    for fp, node in graph.items():
        for imp in node["imports"]:
            if not show_external and imp["external"]:
                continue
            resolved = _resolve_import(fp, imp["module"], graph)
            if resolved and resolved in graph:
                adj[fp].append(resolved)

    cycles = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {fp: WHITE for fp in graph}
    parent = {}

    def dfs(u: str) -> None:
        color[u] = GRAY
        for v in adj[u]:
            if color.get(v) == GRAY:
                # Found a cycle — reconstruct path
                path = [v, u]
                cur = u
                while cur != v and cur in parent:
                    cur = parent[cur]
                    path.append(cur)
                path.reverse()
                cycles.append((v, path))
            elif color.get(v) == WHITE:
                parent[v] = u
                dfs(v)
        color[u] = BLACK

    for fp in list(graph.keys()):
        if color.get(fp) == WHITE:
            dfs(fp)

    return cycles


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def compute_stats(graph: dict, show_external: bool = False) -> dict:
    """Compute aggregate statistics over the dependency graph."""
    total_imports = 0
    unique_modules = set()
    lang_counts = defaultdict(int)

    for fp, node in graph.items():
        lang_counts[node["language"]] += 1
        for imp in node["imports"]:
            if not show_external and imp["external"]:
                continue
            total_imports += 1
            unique_modules.add(imp["module"])

    return {
        "total_files": len(graph),
        "total_imports": total_imports,
        "unique_modules": len(unique_modules),
        "languages": dict(lang_counts),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import/export dependency graph for JS/TS/Python/Rust."
    )
    parser.add_argument("path", help="Root directory or file to analyse")
    parser.add_argument("--depth", type=int, default=DEFAULT_MAX_DEPTH,
                        help="Maximum tree depth (default: 3)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON instead of tree")
    parser.add_argument("--external", action="store_true",
                        help="Include external library imports")
    parser.add_argument("--cycles", action="store_true",
                        help="Detect and report circular dependencies")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"Error: path does not exist: {root}", file=sys.stderr)
        sys.exit(1)

    if root.is_file():
        root = root.parent

    # Build the graph
    graph, project_names = build_graph(root, show_external=args.external)

    if not graph:
        print("No supported source files found.", file=sys.stderr)
        sys.exit(1)

    # --- JSON output ---
    if args.json:
        cycles = []
        if args.cycles:
            cycles = find_cycles(graph, show_external=args.external)

        stats = compute_stats(graph, show_external=args.external)
        # Add circular dependency stats
        if args.cycles:
            stats["circular_dependencies"] = len(cycles)

        output = {
            "root": str(root),
            "project_modules": sorted(project_names),
            "stats": stats,
            "files": list(graph.values()),
        }
        if args.cycles:
            output["cycles"] = [
                {"start": c[0], "path": c[1]} for c in cycles
            ]

        print(json.dumps(output, indent=2, default=str))
        return

    # --- Tree output ---
    # Find entry point(s) — treat top-level files as roots
    top_level = sorted(
        fp for fp in graph
        if os.path.dirname(fp) == str(root)
        or os.path.dirname(fp) == str(root).replace("\\", "/")
    )

    if not top_level:
        # Pick the first file as root
        top_level = [min(graph.keys())]

    print(f"Dependency graph for: {root}\n")
    for entry in top_level:
        tree_lines = render_tree(graph, entry, args.depth)
        for line in tree_lines:
            print(line)
        print()  # blank line between roots

    # --- Cycle report ---
    if args.cycles:
        cycles = find_cycles(graph, show_external=args.external)
        if cycles:
            print(f"\n{'='*60}")
            label = "y" if len(cycles) == 1 else "ies"
            print(f"⚠  {len(cycles)} circular {label} detected\n")
            for start, path in cycles:
                print(f"  Cycle: {' → '.join(path)}")
            print()
        else:
            print("\n✓ No circular dependencies detected.")

    # --- Stats summary ---
    stats = compute_stats(graph, show_external=args.external)
    print(f"\n{'─'*40}")
    print(f"  Files analysed:     {stats['total_files']}")
    print(f"  Total imports:      {stats['total_imports']}")
    print(f"  Unique modules:     {stats['unique_modules']}")
    if stats["languages"]:
        lang_summary = ", ".join(
            f"{lang}: {count}" for lang, count in sorted(stats["languages"].items())
        )
        print(f"  Languages:          {lang_summary}")


if __name__ == "__main__":
    main()