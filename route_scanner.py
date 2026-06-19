#!/usr/bin/env python3
"""
route_scanner.py — Scan frontend routes in React/TypeScript projects.

Detects:
  - All defined frontend routes (React Router, TanStack Router, Next.js)
  - Route parameters and query strings
  - Navigation links and hrefs
  - Route nesting and layout structure
  - Unused routes (routes defined but never linked to)
  - Orphaned page files (files that exist but aren't routed)

Gebruik:
    python route_scanner.py <path>
    python route_scanner.py <path> --json
    python route_scanner.py <path> --unused
    python route_scanner.py <path> --graph
"""
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

EXCLUDE_DIRS = frozenset({
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    "build", "dist", ".next", "out",
})

# Route patterns for different routers
ROUTE_PATTERNS = {
    "react_router_route": re.compile(
        r'<Route\s+(?:path=[\'"]([^\'"]+)[\'"]\s*)?'
        r'(?:\s*element=\{?\s*(?:<(\w+)|(\w+))\s*)'
        r'[^>]*/?>'
    ),
    "react_router_navigate": re.compile(
        r'(?:navigate|push)\s*\(\s*[\'"]([^\'"]+)[\'"]'
    ),
    "react_router_link": re.compile(
        r'<Link\s+[^>]*to=[\'"]([^\'"]+)[\'"]',
    ),
    "react_router_navlink": re.compile(
        r'<NavLink\s+[^>]*to=[\'"]([^\'"]+)[\'"]',
    ),
    "nextjs_link": re.compile(
        r'<Link\s+[^>]*href=[\'"]([^\'"]+)[\'"]',
    ),
    "nextjs_router": re.compile(
        r'router\.(?:push|replace)\s*\(\s*[\'"]([^\'"]+)[\'"]',
    ),
    "tanstack_route": re.compile(
        r'(?:new\s+)?Route\s*\(\s*\{[^}]*path:\s*[\'"]([^\'"]+)[\'"]',
    ),
    "window_location": re.compile(
        r'window\.location\s*=\s*[\'"]([^\'"]+)[\'"]',
    ),
    "anchor_href": re.compile(
        r'<a\s+[^>]*href=[\'"]([^\'"]+)[\'"]',
    ),
    "redirect": re.compile(
        r'(?:redirect|Redirect)\s*\(\s*[\'"]([^\'"]+)[\'"]',
    ),
}

ROUTE_DEFINITION_PATTERNS = [
    re.compile(r'(?:path|to|href)\s*[=:]\s*[\'"]([^\'"]+)[\'"]'),
    re.compile(r'<Route\s+path=[\'"]([^\'"]+)[\'"]'),
    re.compile(r'<Link\s+[^>]*to=[\'"]([^\'"]+)[\'"]'),
    re.compile(r'router\.(?:push|replace|navigate)\s*\(\s*[\'"]([^\'"]+)[\'"]'),
    re.compile(r'navigate\s*\(\s*[\'"]([^\'"]+)[\'"]'),
]

# File patterns for page files
PAGE_FILE_PATTERNS = {
    "pages": r"pages?",
    "index": r"index\.[jt]sx?",
    "slug": r"\[.*?\]\.[jt]sx?",
}

TRAILING_SLASH_NORMALIZE = re.compile(r'/+')


def normalize_route(route: str) -> str:
    """Normalize a route path."""
    route = TRAILING_SLASH_NORMALIZE.sub("/", route)
    route = route.rstrip("/") or "/"
    return route


def is_external_url(route: str) -> bool:
    """Check if a route is an external URL."""
    return route.startswith(("http://", "https://", "mailto:", "tel:", "data:"))


def is_route_definition(content: str, route: str) -> bool:
    """Check if a route appears in a route definition context."""
    for pattern in ROUTE_DEFINITION_PATTERNS:
        for match in pattern.finditer(content):
            if match.group(1) == route:
                return True
    return False


def collect_source_files(root: Path) -> list[Path]:
    """Collect all source files in the project."""
    files = []

    if root.is_file():
        return [root]

    exts = {".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".html", ".json"}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            ext = Path(fn).suffix.lower()
            if ext in exts:
                files.append(Path(dirpath) / fn)

    return sorted(files)


def find_routes_in_file(filepath: Path) -> list[dict]:
    """Find all route references in a single file."""
    routes = []

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return routes

    ext = filepath.suffix.lower()

    for pattern_name, pattern in ROUTE_PATTERNS.items():
        for match in pattern.finditer(content):
            route = match.group(1)
            if route and not is_external_url(route):
                routes.append({
                    "route": normalize_route(route),
                    "file": str(filepath),
                    "pattern": pattern_name,
                    "line": content[:match.start()].count("\n") + 1,
                    "full_match": match.group()[:80],
                })

    # Also scan href attributes in anchor tags
    if ext in (".html", ".tsx", ".jsx"):
        for match in re.finditer(r'href=[\'"]([^\'"]+)[\'"]', content):
            route = match.group(1)
            if route and not is_external_url(route) and not route.startswith("#"):
                routes.append({
                    "route": normalize_route(route),
                    "file": str(filepath),
                    "pattern": "href_attr",
                    "line": content[:match.start()].count("\n") + 1,
                    "full_match": match.group()[:80],
                })

    return routes


def find_nextjs_pages(root: Path) -> list[dict]:
    """Discover routes from Next.js pages directory structure."""
    routes = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        path = Path(dirpath)

        # Check for Next.js app router (app/) or pages router (pages/)
        if path.name in ("app", "pages"):
            # Check if this is actually the Next.js pages directory
            # by looking at parent structure
            pass

        for fn in filenames:
            if fn.endswith((".tsx", ".jsx", ".ts", ".js")):
                fp = path / fn
                # Only consider files in pages/ or app/ directories
                parts = fp.relative_to(root).parts
                if "pages" in parts or "app" in parts:
                    # Convert file path to route
                    route_parts = []
                    for part in parts:
                        if part in ("pages", "app", "index.tsx", "index.jsx", "index.ts", "index.js"):
                            continue
                        if part.startswith("[") and part.endswith("]"):
                            route_parts.append(f":{part[1:-1]}")
                        elif part == "layout.tsx" or part == "layout.jsx":
                            route_parts.append("(layout)")
                        else:
                            route_parts.append(part.replace(".tsx", "").replace(".jsx", "")
                                               .replace(".ts", "").replace(".js", ""))
                    if route_parts:
                        route = "/" + "/".join(route_parts)
                        routes.append({
                            "route": route,
                            "file": str(fp),
                            "pattern": "nextjs_filesystem",
                            "type": "page",
                        })

    return routes


def find_route_files_vite(root: Path) -> list[dict]:
    """Discover routes from file-based routing (Vite React Router)."""
    routes = []

    # Common file-based routing patterns
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn == "routes.ts" or fn == "routes.tsx" or fn == "routes.js" or fn == "routes.jsx":
                routes.append({
                    "route": "(route config)",
                    "file": str(Path(dirpath) / fn),
                    "pattern": "route_config_file",
                    "type": "config",
                })

    return routes


def find_unused_routes(all_routes: list[dict]) -> list[dict]:
    """Find routes that are defined but never referenced."""
    # Group by origin
    definitions = {}
    references = []

    for r in all_routes:
        if r.get("pattern") == "nextjs_filesystem" or r.get("type") == "page":
            definitions[r["route"]] = r
        elif r.get("pattern") in ("react_router_route", "tanstack_route"):
            definitions[r["route"]] = r
        else:
            references.append(r)

    # Check which definitions have references
    referenced_routes = set()
    for ref in references:
        referenced_routes.add(ref["route"])

    # Also check links that point to defined routes
    linked_routes = set()
    for ref in references:
        if ref.get("pattern") in ("react_router_link", "react_router_navlink",
                                   "nextjs_link", "anchor_href"):
            linked_routes.add(ref["route"])

    unused = []
    for route, defn in definitions.items():
        if route not in linked_routes and route not in referenced_routes:
            unused.append(defn)

    return unused


def find_orphaned_pages(all_routes: list[dict], root: Path) -> list[dict]:
    """Find page files that exist but aren't connected to any route."""
    # This is complex; for now, check common patterns
    orphans = []
    page_files = set()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            fp = Path(dirpath) / fn
            ext = fp.suffix.lower()
            if ext in (".tsx", ".jsx"):
                parts = fp.relative_to(root).parts
                if "pages" in parts or "components" in parts:
                    page_files.add(str(fp))

    # Remove files that appear in route definitions
    route_files = {r["file"] for r in all_routes if r.get("file")}
    orphaned_files = page_files - route_files

    for fp in sorted(orphaned_files):
        orphans.append({
            "route": "(orphaned)",
            "file": fp,
            "pattern": "orphaned_page",
            "type": "orphan",
        })

    return orphans


def generate_graph(all_routes: list[dict]) -> str:
    """Generate a simple ASCII route dependency graph."""
    lines = [" Route Graph", "=" * 60]

    # Group by route
    by_route = defaultdict(list)
    for r in all_routes:
        by_route[r["route"]].append(r)

    # Sort routes by depth
    def route_depth(route: str) -> int:
        return len([p for p in route.split("/") if p])

    sorted_routes = sorted(by_route.keys(), key=lambda r: (route_depth(r), r))

    for route in sorted_routes:
        depth = route_depth(route)
        indent = "  " * depth
        prefix = "└─ " if depth > 0 else ""

        refs = by_route[route]
        page_refs = [r for r in refs if r.get("type") == "page"]
        link_refs = [r for r in refs if r.get("pattern",
                     "") not in ("nextjs_filesystem",) and r.get("type") != "page"]

        icon = "📄" if page_refs else "🔗"
        lines.append(f"{indent}{prefix}{icon} {route}")

        # Show linked files
        shown_files = set()
        for ref in refs:
            if ref.get("file") and ref["file"] not in shown_files:
                cwd = Path.cwd()
                fp = Path(ref["file"])
                rel_file = fp.relative_to(cwd) if fp.exists() else ref["file"]
                lines.append(f"{indent}    📁 {rel_file}")
                shown_files.add(ref["file"])

    return "\n".join(lines)


def print_report(all_routes: list[dict], show_unused: bool = False,
                 show_graph: bool = False, root: Path = None) -> None:
    """Print a formatted route report."""
    # Categorize
    by_pattern = defaultdict(list)
    for r in all_routes:
        by_pattern[r["pattern"]].append(r)

    route_patterns = {k for k in by_pattern.keys()
                      if k not in ("react_router_link", "react_router_navlink",
                                    "nextjs_link", "anchor_href", "href_attr")}
    link_patterns = {k for k in by_pattern.keys()
                     if k in ("react_router_link", "react_router_navlink",
                               "nextjs_link", "anchor_href", "href_attr")}

    route_refs = [r for r in all_routes if r["pattern"] in route_patterns]
    link_refs = [r for r in all_routes if r["pattern"] in link_patterns]
    other_refs = [r for r in all_routes if r["pattern"] not in route_patterns | link_patterns]

    unique_routes = sorted(set(r["route"] for r in route_refs))

    print(f"\n{'='*60}")
    print(f" 🗺  ROUTE SCANNER")
    print(f"{'='*60}")
    print(f"   Routes (uniek): {len(unique_routes)}")
    print(f"   Route refs:    {len(route_refs)}")
    print(f"   Link refs:     {len(link_refs)}")
    print()

    if unique_routes:
        print(f" ── Gedefinieerde Routes ({len(unique_routes)}) ──")
        for route in unique_routes:
            refs = [r for r in route_refs if r["route"] == route]
            files = sorted(set(r["file"] for r in refs))
            print(f"   🏷  {route}")
            for f in files[:3]:
                rel = Path(f).relative_to(root) if root else f
                print(f"       📄 {rel}")
            if len(files) > 3:
                print(f"       ... en nog {len(files) - 3} bestanden")
        print()

    if link_refs:
        print(f" ── Navigatie Links ({len(link_refs)}) ──")
        by_link_target = defaultdict(list)
        for r in link_refs:
            by_link_target[r["route"]].append(r)
        for route in sorted(by_link_target.keys()):
            count = len(by_link_target[route])
            print(f"   🔗 {route} ({count}x)")
        print()

    if show_unused and route_refs:
        unused = find_unused_routes(all_routes)
        if unused:
            print(f" ── Ongebruikte Routes ({len(unused)}) ──")
            for r in unused:
                print(f"   ⚠  {r['route']} (gedefinieerd in {Path(r['file']).name})")
        else:
            print(" ✅ Alle routes worden gebruikt")
        print()

    if root:
        orphans = find_orphaned_pages(all_routes, root)
        if orphans:
            print(f" ── Orphaned Page Files ({len(orphans)}) ──")
            for o in orphans[:10]:
                print(f"   💡 {Path(o['file']).relative_to(root)}")
            if len(orphans) > 10:
                print(f"   ... en nog {len(orphans) - 10} meer")
        print()

    if show_graph:
        print(generate_graph(all_routes))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="route_scanner.py — Scan frontend routes in React/TS projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python route_scanner.py .
  python route_scanner.py src/ --json
  python route_scanner.py . --unused
  python route_scanner.py . --graph
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--unused", "-u", action="store_true",
                        help="Toon ongebruikte routes")
    parser.add_argument("--graph", "-g", action="store_true",
                        help="Toon ASCII route dependency graph")
    parser.add_argument("--version", action="version", version="route_scanner.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 Route Scanner v1.0.0 — scanning {target}")

    # Scan files for routes
    files = collect_source_files(target)
    all_routes = []

    for fp in files:
        routes = find_routes_in_file(fp)
        all_routes.extend(routes)

    # Also scan Next.js filesystem routes
    fs_routes = find_nextjs_pages(target)
    all_routes.extend(fs_routes)

    # Find route config files
    config_routes = find_route_files_vite(target)
    all_routes.extend(config_routes)

    if args.json:
        output = {
            "total_routes": len(all_routes),
            "routes": all_routes,
        }
        if args.unused:
            unused = find_unused_routes(all_routes)
            output["unused_routes"] = unused
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print_report(all_routes, args.unused, args.graph, target)


if __name__ == "__main__":
    main()
