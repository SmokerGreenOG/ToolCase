#!/usr/bin/env python3
"""
frontend_backend_linker.py — Find frontend-backend API endpoint mismatches.

Detects:
  - API calls in frontend code that reference undefined backend routes
  - Backend API routes that have no frontend consumers
  - HTTP method mismatches (GET vs POST vs PUT vs DELETE)
  - URL path inconsistencies between frontend and backend
  - Missing or extra URL parameters
  - Inconsistent response types (where detectable)

Gebruik:
    python frontend_backend_linker.py <path>
    python frontend_backend_linker.py <path> --api-prefix /api
    python frontend_backend_linker.py <path> --json
    python frontend_backend_linker.py <path> --fix
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
    "build", "dist", ".next",
        ".backups",

        ".rsi_backups",

        ".rsi_reports",

        ".self_improve_reports",
        })

# Backend route detection patterns
BACKEND_ROUTE_PATTERNS = {
    "python_fastapi": re.compile(
        r'@(?:router|app)\.(?:get|post|put|delete|patch|options|head)\s*\(\s*["\']([^"\']+)["\']',
    ),
    "python_flask": re.compile(
        r'@(?:app|blueprint)\.route\s*\(\s*["\']([^"\']+)["\']',
    ),
    "python_django": re.compile(
        r'(?:path|re_path|url)\s*\(\s*["\'](?:[^"\']*)["\'],\s*(?:views?\.\w+|include)',
    ),
    "rust_axum": re.compile(
        r'\.route\s*\(\s*["\']([^"\']+)["\']',
    ),
    "rust_actix": re.compile(
        r'#[get|post|put|delete|patch]\s*\(\s*["\']([^"\']+)["\']',
    ),
    "ts_express": re.compile(
        r'(?:router|app)\s*\.\s*(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
    ),
    "ts_nextjs_api": re.compile(
        r'(?:export\s+(?:async\s+)?function\s+(?:GET|POST|PUT|DELETE|PATCH)|'
        r'export\s+const\s+(?:GET|POST|PUT|DELETE|PATCH)\s*[=:])',
    ),
}

# Frontend API call patterns
FRONTEND_API_PATTERNS = {
    "fetch": re.compile(
        r'(?:fetch|axios\.(?:get|post|put|delete|patch|request))\s*\(\s*["\']'
        r'([^"\']+)["\']',
    ),
    "axios_instance": re.compile(
        r'api(?:Client|Service)?\s*\.\s*(?:get|post|put|delete|patch|request)\s*\(\s*["\']'
        r'([^"\']+)["\']',
    ),
    "angular_http": re.compile(
        r'this\.http\s*\.\s*(?:get|post|put|delete|patch)\s*\(\s*["\']'
        r'([^"\']+)["\']',
    ),
    "graphql": re.compile(
        r'(?:gql|graphql)\s*`\s*(?:query|mutation|subscription)',
    ),
    "trpc": re.compile(
        r'trpc\s*\.\s*(?:query|mutation|useQuery|useMutation)\s*\(\s*["\']'
        r'([^"\']+)["\']',
    ),
    "tanstack_query": re.compile(
        r'useQuery\s*\(\s*\{[^}]*queryKey:\s*\[[^\]]*["\']([^"\']+)["\']',
    ),
    "websocket": re.compile(
        r'(?:ws|wss)://[^"\'\s]+',
    ),
    "api_route_string": re.compile(
        r'(?:api|apiUrl|API_URL|BASE_URL|baseURL)\s*[+]\s*["\']([^"\']+)["\']',
    ),
}

HTTP_METHOD_PATTERNS = {
    "get": re.compile(r'(?:\.get\s*\(|method:\s*["\']GET["\']|"get")', re.IGNORECASE),
    "post": re.compile(r'(?:\.post\s*\(|method:\s*["\']POST["\']|"post")', re.IGNORECASE),
    "put": re.compile(r'(?:\.put\s*\(|method:\s*["\']PUT["\']|"put")', re.IGNORECASE),
    "delete": re.compile(r'(?:\.delete\s*\(|method:\s*["\']DELETE["\']|"delete")', re.IGNORECASE),
    "patch": re.compile(r'(?:\.patch\s*\(|method:\s*["\']PATCH["\']|"patch")', re.IGNORECASE),
}

BACKEND_METHOD_PATTERNS = {
    "get": re.compile(r'\.(?:get|route)\s*\(\s*["\']'),
    "post": re.compile(r'\.post\s*\(\s*["\']'),
    "put": re.compile(r'\.put\s*\(\s*["\']'),
    "delete": re.compile(r'\.delete\s*\(\s*["\']'),
    "patch": re.compile(r'\.patch\s*\(\s*["\']'),
}

ROUTE_METHOD_MAP = {
    "python_fastapi": ("get", "post", "put", "delete", "patch"),
    "python_flask": ("get", "post", "put", "delete", "patch"),
    "ts_express": ("get", "post", "put", "delete", "patch"),
}


def is_api_call(url: str) -> bool:
    """Check if a URL looks like an API call."""
    return (
        url.startswith("/api/") or
        url.startswith("/") and
        not url.startswith(("#", "/_next", "/static", "/favicon", "/assets"))
    )


def normalize_url(url: str) -> str:
    """Normalize a URL by removing query strings and trailing slashes."""
    # Remove query strings
    url = url.split("?")[0]
    # Remove trailing slash
    url = url.rstrip("/")
    # Collapse double slashes
    while "//" in url:
        url = url.replace("//", "/")
    return url


def extract_route_params(url: str) -> list[str]:
    """Extract route parameters from a URL pattern."""
    params = []
    # Match :param, {param}, [param]
    for m in re.finditer(r"(?:\{(\w+)\}|:(\w+)|\[(\w+)\])", url):
        param = m.group(1) or m.group(2) or m.group(3)
        if param:
            params.append(param)
    return params


def collect_source_files(root: Path) -> list[Path]:
    """Collect all relevant source files."""
    files = []
    exts = {".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".mjs", ".cjs"}

    if root.is_file():
        return [root]

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            ext = Path(fn).suffix.lower()
            if ext in exts:
                files.append(Path(dirpath) / fn)

    return sorted(files)


def scan_backend_routes(root: Path, api_prefix: str) -> list[dict]:
    """Scan for backend API route definitions."""
    routes = []

    for fp in collect_source_files(root):
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        ext = fp.suffix.lower()
        for pattern_name, pattern in BACKEND_ROUTE_PATTERNS.items():
            for match in pattern.finditer(content):
                url = match.group(1) if match.groups() else ""
                if not url:
                    continue

                full_url = url if url.startswith("/") else f"/{url}"
                if not full_url.startswith(api_prefix) and not full_url.startswith("/"):
                    full_url = f"{api_prefix}{full_url}"

                # Detect HTTP method
                line_start = max(0, match.start() - 200)
                context = content[line_start:match.end()]
                method = "GET"  # default
                for m_name, m_pattern in BACKEND_METHOD_PATTERNS.items():
                    if m_pattern.search(context):
                        method = m_name.upper()
                        break

                params = extract_route_params(url)

                routes.append({
                    "route": normalize_url(full_url),
                    "raw_url": url,
                    "file": str(fp),
                    "framework": pattern_name,
                    "method": method,
                    "params": params,
                    "type": "backend",
                })

    return routes


def scan_frontend_calls(root: Path, api_prefix: str) -> list[dict]:
    """Scan for frontend API calls."""
    calls = []

    for fp in collect_source_files(root):
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        ext = fp.suffix.lower()
        if ext in (".py", ".rs"):
            continue  # Skip backend files

        for pattern_name, pattern in FRONTEND_API_PATTERNS.items():
            for match in pattern.finditer(content):
                url = match.group(1) if match.groups() else ""
                if not url:
                    continue

                if not is_api_call(url) and api_prefix not in url:
                    continue

                # Detect HTTP method
                line_start = max(0, match.start() - 100)
                context = content[line_start:match.end()]
                method = "GET"  # default
                for m_name, m_pattern in HTTP_METHOD_PATTERNS.items():
                    if m_pattern.search(context):
                        method = m_name.upper()
                        break

                params = extract_route_params(url)

                calls.append({
                    "route": normalize_url(url),
                    "raw_url": url,
                    "file": str(fp),
                    "pattern": pattern_name,
                    "method": method,
                    "params": params,
                    "type": "frontend",
                })

    return calls


def match_routes(backend_routes: list[dict], frontend_calls: list[dict],
                 api_prefix: str) -> dict:
    """Cross-reference frontend calls with backend routes."""
    backend_by_route = {}
    for br in backend_routes:
        route_key = br["route"]
        if route_key not in backend_by_route:
            backend_by_route[route_key] = []
        backend_by_route[route_key].append(br)

    frontend_by_route = {}
    for fc in frontend_calls:
        route_key = fc["route"]
        if route_key not in frontend_by_route:
            frontend_by_route[route_key] = []
        frontend_by_route[route_key].append(fc)

    # Matched routes
    matched = []
    backend_routes_set = set(backend_by_route.keys())
    frontend_routes_set = set(frontend_by_route.keys())
    matched_routes = backend_routes_set & frontend_routes_set

    for route in sorted(matched_routes):
        brs = backend_by_route[route]
        fcs = frontend_by_route[route]
        method_match = any(b["method"] == f["method"] for b in brs for f in fcs)
        param_match = all(
            set(b.get("params", [])) == set(f.get("params", []))
            for b in brs for f in fcs
        )

        matched.append({
            "route": route,
            "status": "MATCHED",
            "method_match": method_match,
            "param_match": param_match,
            "backend_count": len(brs),
            "frontend_count": len(fcs),
            "backend_files": sorted(set(b["file"] for b in brs)),
            "frontend_files": sorted(set(f["file"] for f in fcs)),
        })

    # Orphaned backend routes
    orphaned_backend = []
    for route in sorted(backend_routes_set - frontend_routes_set):
        for br in backend_by_route[route]:
            orphaned_backend.append(br)

    # Orphaned frontend calls
    orphaned_frontend = []
    for route in sorted(frontend_routes_set - backend_routes_set):
        for fc in frontend_by_route[route]:
            orphaned_frontend.append(fc)

    # Method mismatches
    method_mismatches = []
    for route in sorted(matched_routes):
        brs = backend_by_route[route]
        fcs = frontend_by_route[route]
        br_methods = set(b["method"] for b in brs)
        fc_methods = set(f["method"] for f in fcs)
        if br_methods != fc_methods:
            method_mismatches.append({
                "route": route,
                "backend_methods": list(br_methods),
                "frontend_methods": list(fc_methods),
                "backend_files": sorted(set(b["file"] for b in brs)),
                "frontend_files": sorted(set(f["file"] for f in fcs)),
            })

    # Param mismatches
    param_mismatches = []
    for route in sorted(matched_routes):
        brs = backend_by_route[route]
        fcs = frontend_by_route[route]
        br_params = set()
        for b in brs:
            br_params.update(b.get("params", []))
        fc_params = set()
        for f in fcs:
            fc_params.update(f.get("params", []))

        missing_backend = fc_params - br_params
        missing_frontend = br_params - fc_params
        if missing_backend or missing_frontend:
            param_mismatches.append({
                "route": route,
                "backend_params": list(br_params),
                "frontend_params": list(fc_params),
                "missing_in_backend": list(missing_backend),
                "missing_in_frontend": list(missing_frontend),
            })

    return {
        "matched": matched,
        "orphaned_backend": orphaned_backend,
        "orphaned_frontend": orphaned_frontend,
        "method_mismatches": method_mismatches,
        "param_mismatches": param_mismatches,
    }


def print_report(stats: dict, api_prefix: str) -> None:
    """Print a formatted report."""
    matched = stats["matched"]
    orphaned_backend = stats["orphaned_backend"]
    orphaned_frontend = stats["orphaned_frontend"]
    method_mismatches = stats["method_mismatches"]
    param_mismatches = stats["param_mismatches"]

    print(f"\n{'='*60}")
    print(f" 🔗 FRONTEND-BACKEND LINKER")
    print(f"{'='*60}")
    print(f"   API prefix: {api_prefix}")
    print(f"   ✅ Matched routes:  {len(matched)}")
    print(f"   ⚠  Orphaned backend: {len(orphaned_backend)}")
    print(f"   ⚠  Orphaned frontend: {len(orphaned_frontend)}")
    print(f"   ❌ Method mismatches: {len(method_mismatches)}")
    print(f"   🏷  Param mismatches:  {len(param_mismatches)}")
    print()

    if matched:
        print(f" ── Matched Routes ({len(matched)}) ──")
        for m in matched[:15]:
            icon = "✅" if m["method_match"] and m["param_match"] else "⚠"
            print(f"   {icon} {m['route']}")
            if not m["method_match"]:
                print(f"       Method mismatch!")
            if not m["param_match"]:
                print(f"       Parameter mismatch!")
        if len(matched) > 15:
            print(f"   ... en nog {len(matched) - 15} routes")
        print()

    if orphaned_backend:
        print(f" ── Orphaned Backend Routes ({len(orphaned_backend)}) ──")
        for br in orphaned_backend[:10]:
            cwd = Path.cwd()
            fp = Path(br["file"])
            rel_file = fp.relative_to(cwd) if fp.exists() else br["file"]
            print(f"   ⚠  [{br['method']}] {br['route']}  ({rel_file})")
        if len(orphaned_backend) > 10:
            print(f"   ... en nog {len(orphaned_backend) - 10} routes")
        print()

    if orphaned_frontend:
        print(f" ── Orphaned Frontend Calls ({len(orphaned_frontend)}) ──")
        for fc in orphaned_frontend[:10]:
            cwd = Path.cwd()
            fp = Path(fc["file"])
            rel_file = fp.relative_to(cwd) if fp.exists() else fc["file"]
            print(f"   ⚠  [{fc['method']}] {fc['route']}  ({rel_file}: line)")
        if len(orphaned_frontend) > 10:
            print(f"   ... en nog {len(orphaned_frontend) - 10} calls")
        print()

    if method_mismatches:
        print(f" ── Method Mismatches ({len(method_mismatches)}) ──")
        for mm in method_mismatches:
            print(f"   ❌ {mm['route']}")
            print(f"       Backend: {', '.join(mm['backend_methods'])}")
            print(f"       Frontend: {', '.join(mm['frontend_methods'])}")
        print()

    if param_mismatches:
        print(f" ── Parameter Mismatches ({len(param_mismatches)}) ──")
        for pm in param_mismatches:
            print(f"   🏷  {pm['route']}")
            if pm["missing_in_backend"]:
                print(f"       Ontbreekt in backend: {', '.join(pm['missing_in_backend'])}")
            if pm["missing_in_frontend"]:
                print(f"       Ontbreekt in frontend: {', '.join(pm['missing_in_frontend'])}")
        print()


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="frontend_backend_linker.py — Cross-ref frontend/backend API endpoints",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python frontend_backend_linker.py .
  python frontend_backend_linker.py . --api-prefix /api/v1
  python frontend_backend_linker.py . --json
  python frontend_backend_linker.py . --fix
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root")
    parser.add_argument("--api-prefix", "-p", default="/api",
                        help="API prefix voor backend routes (default: /api)")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--fix", "-f", action="store_true",
                        help="Probeer mismatches te fixen (experimenteel)")
    parser.add_argument("--version", action="version",
                        version="frontend_backend_linker.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 Frontend-Backend Linker v1.0.0 — scanning {target}")

    backend_routes = scan_backend_routes(target, args.api_prefix)
    frontend_calls = scan_frontend_calls(target, args.api_prefix)

    print(f"   Backend routes: {len(backend_routes)}")
    print(f"   Frontend calls: {len(frontend_calls)}")

    stats = match_routes(backend_routes, frontend_calls, args.api_prefix)

    if args.json:
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    else:
        print_report(stats, args.api_prefix)


if __name__ == "__main__":
    main()
