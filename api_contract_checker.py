#!/usr/bin/env python3
"""
api_contract_checker.py — Detect frontend-backend API contract mismatches.

Scans frontend (.ts, .tsx, .js, .jsx) and backend (.py, .rs, .ts) files
to surface inconsistencies between what the frontend expects and what the
backend actually delivers.

Detects:
  - Endpoint path mismatch (orphaned frontend calls / backend routes)
  - HTTP method mismatch (GET vs POST vs PUT vs DELETE vs PATCH)
  - Request body field mismatch (e.g. frontend sends 'path' but backend expects 'folderPath')
  - Response field mismatch (frontend destructures fields the backend never returns)
  - Missing error handling (API calls without .catch, try/except, or error callbacks)
  - Missing loading state (no isLoading/loading/useBoolean usage around the call)
  - Implicit content-type mismatch (frontend expects JSON but backend sends text/plain)

Gebruik:
    python api_contract_checker.py <path>
    python api_contract_checker.py <path> --api-prefix /api/v1
    python api_contract_checker.py <path> --json
    python api_contract_checker.py <path> --strict
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
    "build", "dist", ".next", "out", "coverage", ".tox",
        ".backups",
        
        ".rsi_backups",
        
        ".rsi_reports",
        
        ".self_improve_reports",
        })

# Styles — dark purple / neon theme
STYLE = {
    "header": "\033[95m",       # magenta / purple
    "ok": "\033[92m",           # green
    "warn": "\033[93m",         # yellow
    "fail": "\033[91m",         # red
    "info": "\033[96m",         # cyan
    "bold": "\033[1m",
    "dim": "\033[2m",
    "reset": "\033[0m",
}

# ---------------------------------------------------------------------------
# Regex patterns — Frontend
# ---------------------------------------------------------------------------

# API-call patterns: method + url
FRONTEND_CALL_METHOD_RE = re.compile(
    r'(?P<method>get|post|put|delete|patch|request)'
    r'\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

FRONTEND_FETCH_RE = re.compile(
    r'(?:fetch|axios)\s*\(\s*["\']([^"\']+)["\']',
)

FRONTEND_QUERY_RE = re.compile(
    r'(?:useQuery|useMutation|useSuspenseQuery)\s*\('
    r'(?:\s*\{[^}]*queryKey\s*:\s*\[[^\]]*["\']([^"\']+)["\'])?',
)

# Request body fields in frontend (object literal passed as second arg body/data)
FRONTEND_BODY_FIELDS_RE = re.compile(
    r'(?:body|data)\s*:\s*(?:JSON\.stringify\s*)?'
    r'\{\s*([^}]+)\s*\}',
    re.DOTALL,
)

# Extract individual key-value pairs from a body snippet
FIELD_KEY_RE = re.compile(
    r'(?:["\']?(\w+)["\']?\s*:|\b(\w+)\s*[,}])',
)

# Try / catch detection around API calls
HAS_TRY_CATCH_RE = re.compile(
    r'try\s*\{[^}]*?(?:fetch|axios|await)\s*\([^}]*\}\s*catch\s*\(',
    re.DOTALL,
)

# .catch() on promises
HAS_CATCH_RE = re.compile(
    r'\.catch\s*\(',
)

# .then() without .catch()
THEN_ONLY_RE = re.compile(
    r'\.then\s*\(',
)

# Loading state checks
LOADING_INDICATORS_RE = re.compile(
    r'\b(isLoading|loading|isFetching|useBoolean|setLoading|LOADING)\b',
)

# Frontend response destructuring patterns
FRONTEND_RESPONSE_FIELDS_RE = re.compile(
    r'(?:const|let|var)\s*\{([^}]+)\}\s*=\s*(?:res|response|data|result)\b',
)

# Frontend expects json()
FRONTEND_JSON_EXPECT_RE = re.compile(
    r'\.json\s*\(\)',
)

# Frontend expects text()
FRONTEND_TEXT_EXPECT_RE = re.compile(
    r'\.text\s*\(\)',
)

# ---------------------------------------------------------------------------
# Regex patterns — Backend
# ---------------------------------------------------------------------------

# Python: FastAPI / Flask / Starlette routes
BACKEND_PYTHON_DECORATOR_RE = re.compile(
    r'@(?:app|router|blueprint)\s*\.\s*'
    r'(?P<method>get|post|put|delete|patch|options|route)'
    r'\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# Python: Django url / path
BACKEND_DJANGO_URL_RE = re.compile(
    r'(?:path|re_path|url)\s*\(\s*["\']([^"\']+)["\']',
)

# Python: Pydantic / dataclass request body models
BACKEND_PYTHON_BODY_MODEL_RE = re.compile(
    r'class\s+(\w+)\s*\((?:BaseModel|pydantic\.BaseModel|dataclass)\)',
)

# Python: Pydantic model fields
BACKEND_PYTHON_MODEL_FIELDS_RE = re.compile(
    r'^\s*(\w+)\s*:\s*(?:\w+\s*=\s*Field|\w+|\w+\s*=\s*None|\w+\s*=\s*\.\.\.)',
    re.MULTILINE,
)

# Python: return response types
BACKEND_PYTHON_RESPONSE_RE = re.compile(
    r'(?:return\s+(?:JSONResponse|Response|PlainTextResponse|HTMLResponse|RedirectResponse)\s*\('
    r'|Response\s*\('
    r'|JSONResponse\s*\('
    r'|PlainTextResponse\s*\('
    r')',
)

BACKEND_PYTHON_JSON_RESPONSE_RE = re.compile(
    r'(?:JSONResponse|return\s*\{|\s*return\s+\w+\s*\.\s*json\s*\()',
)

BACKEND_PYTHON_TEXT_RESPONSE_RE = re.compile(
    r'(?:PlainTextResponse|return\s*["\'])',
)

# Rust: Axum / Actix route handlers
BACKEND_RUST_ROUTE_RE = re.compile(
    r'\.route\s*\(\s*["\']([^"\']+)["\']\s*,',
)

BACKEND_RUST_METHOD_RE = re.compile(
    r'(?P<method>get|post|put|delete|patch)_service\s*\(',
)

BACKEND_RUST_ATTR_RE = re.compile(
    r'#\[(?P<method>get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# Rust: struct body fields (Json<Struct> or Form<Struct>)
BACKEND_RUST_STRUCT_FIELDS_RE = re.compile(
    r'struct\s+(\w+)\s*\{([^}]+)\}',
    re.DOTALL,
)
BACKEND_RUST_FIELD_RE = re.compile(
    r'(\w+)\s*:\s*(?:\w+|Option<\w+>)',
)

# TypeScript backend (Express / NestJS / tRPC)
BACKEND_TS_ROUTE_RE = re.compile(
    r'(?:router|app|controller|server)\s*\.\s*'
    r'(?P<method>get|post|put|delete|patch|all)'
    r'\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# TypeScript NestJS decorators
BACKEND_NESTJS_DECORATOR_RE = re.compile(
    r'@(?P<method>Get|Post|Put|Delete|Patch)\s*\(\s*["\']([^"\']+)["\']',
)

# TypeScript response types
BACKEND_TS_RESPONSE_TYPE_RE = re.compile(
    r'(?:res\.(?:json|send)\s*\(|return\s+(?:res|response)\s*\.\s*(?:json|send)\s*\()',
)

BACKEND_TS_TEXT_RESPONSE_RE = re.compile(
    r'(?:res\.send\s*\(\s*["\']|res\.send\s*\(\s*\d+)',
)

# TypeScript interface / type definitions for request/response shapes
BACKEND_TS_INTERFACE_FIELDS_RE = re.compile(
    r'(?:interface|type)\s+(\w+)\s*(?:extends\s+\w+\s*)?\{([^}]+)\}',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def style(text: str, *codes: str) -> str:
    """Apply ANSI style codes if output is a TTY."""
    if not sys.stdout.isatty():
        return text
    prefix = "".join(STYLE.get(c, "") for c in codes)
    return f"{prefix}{text}{STYLE['reset']}"


def colorise_severity(count: int, zero_label: str = "none") -> str:
    """Return a coloured label based on the count."""
    if count == 0:
        return style(f"  {zero_label}", "ok", "dim")
    if count <= 3:
        return style(f"  {count}", "warn")
    return style(f"  {count}", "fail", "bold")


def normalize_url(url: str) -> str:
    """Normalise a route URL: strip query, trailing slash, collapse //."""
    url = url.split("?")[0]
    url = url.rstrip("/")
    while "//" in url:
        url = url.replace("//", "/")
    return url


def is_api_call(url: str, api_prefix: str) -> bool:
    """Heuristic: does this look like an API endpoint call?"""
    return (
        url.startswith(api_prefix)
        or (url.startswith("/") and not url.startswith((
            "/_next", "/static", "/favicon", "/assets", "/fonts",
            "#", "http://", "https://",
        )))
    )


def extract_fields_from_body(body_snippet: str) -> set[str]:
    """Extract field names from a JSON-ish body snippet."""
    fields: set[str] = set()
    # Simple key: value or key:value matching
    for m in re.finditer(r'["\']?(\w+)["\']?\s*:', body_snippet):
        fields.add(m.group(1))
    return fields


def extract_fields_from_interface(body: str) -> set[str]:
    """Extract field names from a TypeScript interface/type body."""
    fields: set[str] = set()
    for m in re.finditer(r'^\s*(\w+)\s*[?:]\s*\w+', body, re.MULTILINE):
        fields.add(m.group(1))
    return fields


def extract_fields_from_python_model(body: str) -> set[str]:
    """Extract field names from a Pydantic model body."""
    fields: set[str] = set()
    for m in BACKEND_PYTHON_MODEL_FIELDS_RE.finditer(body):
        fields.add(m.group(1))
    return fields


def extract_fields_from_rust_struct(body: str) -> set[str]:
    """Extract field names from a Rust struct body."""
    fields: set[str] = set()
    for m in BACKEND_RUST_FIELD_RE.finditer(body):
        fields.add(m.group(1))
    return fields


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------


def collect_source_files(root: Path) -> list[Path]:
    """Collect relevant source files, respecting exclude dirs."""
    files: list[Path] = []

    if root.is_file():
        return [root]

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            fp = Path(dirpath) / fn
            ext = fp.suffix.lower()
            if ext in {".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".mjs", ".cjs"}:
                files.append(fp)

    return sorted(files)


# ---------------------------------------------------------------------------
# Frontend scanning
# ---------------------------------------------------------------------------

FrontendCall = dict
Issue = dict


def scan_frontend_files(root: Path, api_prefix: str) -> list[FrontendCall]:
    """Scan frontend (.ts,.tsx,.js,.jsx) files for API calls and metadata."""
    calls: list[FrontendCall] = []

    for fp in collect_source_files(root):
        ext = fp.suffix.lower()
        if ext in {".py", ".rs"}:
            continue  # backend-only

        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        rel_path = str(fp.relative_to(root)) if fp.is_relative_to(root) else str(fp)

        # --- Detect API calls ---
        for match in FRONTEND_CALL_METHOD_RE.finditer(content):
            method = match.group("method").upper()
            url = normalize_url(match.group(2))

            if not is_api_call(url, api_prefix):
                continue

            # Line number
            line_no = content[:match.start()].count("\n") + 1

            # Surrounding context for deeper analysis
            ctx_start = max(0, match.start() - 300)
            ctx_end = min(len(content), match.end() + 300)
            context = content[ctx_start:ctx_end]

            # --- Request body fields ---
            body_fields: set[str] = set()
            for bm in FRONTEND_BODY_FIELDS_RE.finditer(context):
                body_fields.update(extract_fields_from_body(bm.group(1)))

            # Also look for body/data objects in the call arguments
            # Try to find the full call: method(url, {body: {...}})
            paren_depth = 0
            call_end = match.end()
            for i, ch in enumerate(content[match.end():], start=match.end()):
                if ch == "(":
                    paren_depth += 1
                elif ch == ")":
                    if paren_depth == 0:
                        call_end = i + 1
                        break
                    paren_depth -= 1
            call_snippet = content[match.start():call_end]
            for bm in FRONTEND_BODY_FIELDS_RE.finditer(call_snippet):
                body_fields.update(extract_fields_from_body(bm.group(1)))

            # --- Response destructured fields ---
            response_fields: set[str] = set()
            for rm in FRONTEND_RESPONSE_FIELDS_RE.finditer(context):
                for f in re.finditer(r'\b(\w+)\b', rm.group(1)):
                    fname = f.group(1)
                    if fname not in {"res", "response", "data", "result", "await"}:
                        response_fields.add(fname)

            # --- Error handling ---
            has_try_catch = bool(HAS_TRY_CATCH_RE.search(context))
            has_catch = bool(HAS_CATCH_RE.search(context))
            missing_error_handling = not (has_try_catch or has_catch)

            # If there's a .then() but no .catch(), flag it
            has_then = bool(THEN_ONLY_RE.search(context))

            # --- Loading state ---
            has_loading = bool(LOADING_INDICATORS_RE.search(context[:ctx_end]))

            # --- JSON / text expectation ---
            expects_json = bool(FRONTEND_JSON_EXPECT_RE.search(context))
            expects_text = bool(FRONTEND_TEXT_EXPECT_RE.search(context))

            calls.append({
                "type": "frontend",
                "file": rel_path,
                "line": line_no,
                "method": method,
                "url": url,
                "body_fields": sorted(body_fields),
                "response_fields": sorted(response_fields),
                "missing_error_handling": missing_error_handling,
                "has_try_catch": has_try_catch,
                "has_catch": has_catch,
                "has_then_no_catch": has_then and not has_catch,
                "has_loading": has_loading,
                "missing_loading_state": not has_loading,
                "expects_json": expects_json,
                "expects_text": expects_text,
            })

    return calls


# ---------------------------------------------------------------------------
# Backend scanning
# ---------------------------------------------------------------------------

BackendRoute = dict


def scan_backend_files(root: Path, api_prefix: str) -> list[BackendRoute]:
    """Scan backend (.py, .rs, .ts) files for route handlers and their schemas."""
    routes: list[BackendRoute] = []

    for fp in collect_source_files(root):
        ext = fp.suffix.lower()
        if ext not in {".py", ".rs", ".ts", ".tsx", ".js", ".jsx"}:
            continue

        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        rel_path = str(fp.relative_to(root)) if fp.is_relative_to(root) else str(fp)

        # --- Detect backend route definitions ---
        if ext in {".py"}:
            _scan_python_backend(routes, content, rel_path)
        elif ext in {".rs"}:
            _scan_rust_backend(routes, content, rel_path)
        elif ext in {".ts", ".tsx"}:
            _scan_ts_backend(routes, content, rel_path)
        # Also scan .js/.jsx as potential backend (Node.js/Express)
        if ext in {".js", ".jsx"} and ext not in {".ts", ".tsx"}:
            _scan_ts_backend(routes, content, rel_path)

    return routes


def _scan_python_backend(routes: list, content: str, rel_path: str) -> None:
    """Scan Python files for FastAPI/Flask/Django routes."""
    # Decorator-style routes
    for match in BACKEND_PYTHON_DECORATOR_RE.finditer(content):
        method = match.group("method").upper()
        url = normalize_url(match.group(2))

        line_no = content[:match.start()].count("\n") + 1

        # Context for body/response analysis
        ctx_end = min(len(content), match.end() + 1000)
        context = content[match.start():ctx_end]

        # Detect response type
        has_json_response = bool(BACKEND_PYTHON_JSON_RESPONSE_RE.search(context))
        has_text_response = bool(BACKEND_PYTHON_TEXT_RESPONSE_RE.search(context))

        # Look for Pydantic model references in function signature
        body_fields: set[str] = set()
        response_fields: set[str] = set()

        # Try to find referenced Pydantic model
        for model_match in BACKEND_PYTHON_BODY_MODEL_RE.finditer(content):
            model_name = model_match.group(1)
            # Find the model class body
            model_start = model_match.end()
            brace_count = 0
            model_body = ""
            for i in range(model_start, min(len(content), model_start + 2000)):
                if content[i] == "(":
                    brace_count += 1
                elif content[i] == ")":
                    brace_count -= 1
                    if brace_count < 0:
                        model_body = content[model_start:i]
                        break
            if model_body:
                body_fields.update(extract_fields_from_python_model(model_body))

        routes.append({
            "type": "backend",
            "file": rel_path,
            "line": line_no,
            "framework": "python",
            "method": method,
            "url": url,
            "body_fields": sorted(body_fields),
            "response_fields": sorted(response_fields),
            "response_type": (
                "json" if has_json_response
                else "text" if has_text_response
                else "unknown"
            ),
        })


def _scan_rust_backend(routes: list, content: str, rel_path: str) -> None:
    """Scan Rust files for Axum/Actix routes."""
    # Attribute-style routes (Actix)
    for match in BACKEND_RUST_ATTR_RE.finditer(content):
        method = match.group("method").upper()
        url = normalize_url(match.group(2))
        line_no = content[:match.start()].count("\n") + 1

        routes.append({
            "type": "backend",
            "file": rel_path,
            "line": line_no,
            "framework": "rust_actix",
            "method": method,
            "url": url,
            "body_fields": [],
            "response_fields": [],
            "response_type": "unknown",
        })

    # Chained .route() patterns (Axum)
    for match in BACKEND_RUST_ROUTE_RE.finditer(content):
        url = normalize_url(match.group(1))
        # Look for method_service before this .route call
        pre_context = content[max(0, match.start() - 300):match.end()]
        method = "GET"
        for mm in BACKEND_RUST_METHOD_RE.finditer(pre_context):
            method = mm.group("method").upper()

        line_no = content[:match.start()].count("\n") + 1

        routes.append({
            "type": "backend",
            "file": rel_path,
            "line": line_no,
            "framework": "rust_axum",
            "method": method,
            "url": url,
            "body_fields": [],
            "response_fields": [],
            "response_type": "unknown",
        })


def _scan_ts_backend(routes: list, content: str, rel_path: str) -> None:
    """Scan TS/JS files for Express/NestJS routes."""
    # Express-style router.method()
    for match in BACKEND_TS_ROUTE_RE.finditer(content):
        method = match.group("method").upper()
        url = normalize_url(match.group(2))
        line_no = content[:match.start()].count("\n") + 1

        ctx_end = min(len(content), match.end() + 500)
        context = content[match.start():ctx_end]

        has_json = bool(BACKEND_TS_RESPONSE_TYPE_RE.search(context))
        has_text = bool(BACKEND_TS_TEXT_RESPONSE_RE.search(context))

        # Look for request/response interfaces
        body_fields: set[str] = set()
        response_fields: set[str] = set()

        routes.append({
            "type": "backend",
            "file": rel_path,
            "line": line_no,
            "framework": "express",
            "method": method,
            "url": url,
            "body_fields": sorted(body_fields),
            "response_fields": sorted(response_fields),
            "response_type": "json" if has_json else "text" if has_text else "unknown",
        })

    # NestJS decorators
    for match in BACKEND_NESTJS_DECORATOR_RE.finditer(content):
        method = match.group("method").upper()
        url = normalize_url(match.group(2))
        line_no = content[:match.start()].count("\n") + 1

        routes.append({
            "type": "backend",
            "file": rel_path,
            "line": line_no,
            "framework": "nestjs",
            "method": method,
            "url": url,
            "body_fields": [],
            "response_fields": [],
            "response_type": "unknown",
        })


# ---------------------------------------------------------------------------
# Analysis / comparison
# ---------------------------------------------------------------------------


def analyze_contracts(
    frontend_calls: list[FrontendCall],
    backend_routes: list[BackendRoute],
) -> dict:
    """Cross-reference frontend calls with backend routes and produce issues."""
    issues: list[Issue] = []

    # Index backend routes by URL
    backend_by_url: dict[str, list[BackendRoute]] = defaultdict(list)
    for br in backend_routes:
        backend_by_url[br["url"]].append(br)

    frontend_by_url: dict[str, list[FrontendCall]] = defaultdict(list)
    for fc in frontend_calls:
        frontend_by_url[fc["url"]].append(fc)

    backend_urls = set(backend_by_url.keys())
    frontend_urls = set(frontend_by_url.keys())
    matched_urls = backend_urls & frontend_urls
    orphaned_backend_urls = backend_urls - frontend_urls
    orphaned_frontend_urls = frontend_urls - backend_urls

    # --- 1. Endpoint path mismatches (orphaned) ---
    endpoint_mismatches: list[Issue] = []
    for url in sorted(orphaned_backend_urls):
        for br in backend_by_url[url]:
            endpoint_mismatches.append({
                "type": "endpoint_path_mismatch",
                "severity": "warning",
                "detail": f"Backend route [{br['method']}] {br['url']} has no frontend consumer",
                "file": br["file"],
                "line": br["line"],
                "url": br["url"],
                "method": br["method"],
                "side": "backend",
            })
    for url in sorted(orphaned_frontend_urls):
        for fc in frontend_by_url[url]:
            endpoint_mismatches.append({
                "type": "endpoint_path_mismatch",
                "severity": "warning",
                "detail": f"Frontend call [{fc['method']}] {fc['url']} has no backend handler",
                "file": fc["file"],
                "line": fc["line"],
                "url": fc["url"],
                "method": fc["method"],
                "side": "frontend",
            })
    issues.extend(endpoint_mismatches)

    # --- 2. HTTP method mismatches ---
    method_mismatches: list[Issue] = []
    for url in sorted(matched_urls):
        brs = backend_by_url[url]
        fcs = frontend_by_url[url]
        br_methods = set(b["method"] for b in brs)
        fc_methods = set(f["method"] for f in fcs)
        if br_methods != fc_methods:
            for fc in fcs:
                if fc["method"] not in br_methods:
                    method_mismatches.append({
                        "type": "method_mismatch",
                        "severity": "error",
                        "detail": (
                            f"Frontend calls {fc['url']} with {fc['method']} "
                            f"but backend only supports {', '.join(sorted(br_methods))}"
                        ),
                        "file": fc["file"],
                        "line": fc["line"],
                        "url": fc["url"],
                        "frontend_method": fc["method"],
                        "backend_methods": sorted(br_methods),
                    })
    issues.extend(method_mismatches)

    # --- 3. Request body field mismatches ---
    body_field_issues: list[Issue] = []
    for url in sorted(matched_urls):
        brs = backend_by_url[url]
        fcs = frontend_by_url[url]
        for fc in fcs:
            if not fc["body_fields"]:
                continue
            for br in brs:
                if not br["body_fields"]:
                    continue
                backend_fields = set(br["body_fields"])
                frontend_fields = set(fc["body_fields"])
                missing_in_backend = frontend_fields - backend_fields
                missing_in_frontend = backend_fields - frontend_fields
                if missing_in_backend:
                    body_field_issues.append({
                        "type": "body_field_mismatch",
                        "severity": "error",
                        "detail": (
                            f"Frontend sends fields {', '.join(sorted(missing_in_backend))} "
                            f"in {fc['url']} body but backend model doesn't expect them"
                        ),
                        "file": fc["file"],
                        "line": fc["line"],
                        "url": url,
                        "missing_in_backend": sorted(missing_in_backend),
                        "missing_in_frontend": sorted(missing_in_frontend),
                    })
    issues.extend(body_field_issues)

    # --- 4. Response field mismatches ---
    response_field_issues: list[Issue] = []
    for url in sorted(matched_urls):
        brs = backend_by_url[url]
        fcs = frontend_by_url[url]
        for fc in fcs:
            if not fc["response_fields"]:
                continue
            for br in brs:
                if not br["response_fields"]:
                    continue
                backend_resp = set(br["response_fields"])
                frontend_resp = set(fc["response_fields"])
                missing = frontend_resp - backend_resp
                if missing:
                    response_field_issues.append({
                        "type": "response_field_mismatch",
                        "severity": "error",
                        "detail": (
                            f"Frontend expects fields {', '.join(sorted(missing))} "
                            f"in response from {url} but backend never returns them"
                        ),
                        "file": fc["file"],
                        "line": fc["line"],
                        "url": url,
                        "missing_fields": sorted(missing),
                    })
    issues.extend(response_field_issues)

    # --- 5. Missing error handling ---
    missing_error_issues: list[Issue] = []
    for fc in frontend_calls:
        if fc["missing_error_handling"]:
            missing_error_issues.append({
                "type": "missing_error_handling",
                "severity": "warning",
                "detail": f"No .catch() or try/catch found around API call to {fc['url']}",
                "file": fc["file"],
                "line": fc["line"],
                "url": fc["url"],
            })
    issues.extend(missing_error_issues)

    # --- 6. Missing loading state ---
    missing_loading_issues: list[Issue] = []
    for fc in frontend_calls:
        if fc["missing_loading_state"]:
            missing_loading_issues.append({
                "type": "missing_loading_state",
                "severity": "warning",
                "detail": f"No loading state indicator near API call to {fc['url']}",
                "file": fc["file"],
                "line": fc["line"],
                "url": fc["url"],
            })
    issues.extend(missing_loading_issues)

    # --- 7. Frontend expects JSON but backend sends text ---
    content_type_issues: list[Issue] = []
    for url in sorted(matched_urls):
        brs = backend_by_url[url]
        fcs = frontend_by_url[url]
        for fc in fcs:
            if not fc["expects_json"]:
                continue
            for br in brs:
                if br["response_type"] == "text":
                    content_type_issues.append({
                        "type": "content_type_mismatch",
                        "severity": "error",
                        "detail": (
                            f"Frontend expects .json() from {url} "
                            f"but backend sends text response"
                        ),
                        "file": fc["file"],
                        "line": fc["line"],
                        "url": url,
                    })
    issues.extend(content_type_issues)

    # Summary stats
    stats = {
        "frontend_calls": len(frontend_calls),
        "backend_routes": len(backend_routes),
        "matched_endpoints": len(matched_urls),
        "total_issues": len(issues),
        "issues_by_type": defaultdict(int),
        "issues_by_severity": defaultdict(int),
    }
    for issue in issues:
        stats["issues_by_type"][issue["type"]] += 1
        stats["issues_by_severity"][issue["severity"]] += 1

    return {
        "stats": dict(stats),
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(result: dict) -> None:
    """Print a human-readable report with purple/neon styling."""
    stats = result["stats"]
    issues = result["issues"]

    # Group issues by type for display
    by_type: dict[str, list[Issue]] = defaultdict(list)
    for issue in issues:
        by_type[issue["type"]].append(issue)

    s = style

    print()
    print(f"{s('='*62, 'header', 'bold')}")
    print(f" {s('✦ API CONTRACT CHECKER', 'header', 'bold')}")
    print(f"{s('='*62, 'header', 'bold')}")

    # Summary
    print(f"\n {s('📊 Summary', 'info', 'bold')}")
    print(f"   Frontend calls:     {stats['frontend_calls']}")
    print(f"   Backend routes:     {stats['backend_routes']}")
    print(f"   Matched endpoints:  {stats['matched_endpoints']}")
    print(f"   Total issues:       {colorise_severity(stats['total_issues'])}")
    print()

    # Per-type sections
    type_labels = {
        "endpoint_path_mismatch": ("🛤️  Endpoint Path Mismatches", "warn"),
        "method_mismatch": ("🔀 HTTP Method Mismatches", "fail"),
        "body_field_mismatch": ("📦 Request Body Field Mismatches", "fail"),
        "response_field_mismatch": ("📨 Response Field Mismatches", "fail"),
        "missing_error_handling": ("⚠️  Missing Error Handling", "warn"),
        "missing_loading_state": ("⏳ Missing Loading State", "warn"),
        "content_type_mismatch": ("📄 Content-Type Mismatch", "fail"),
    }

    for ttype, (label, sev_style) in type_labels.items():
        items = by_type.get(ttype, [])
        if not items:
            continue
        print(f" {s(f'── {label} ({len(items)}) ──', sev_style, 'bold')}")
        for item in items[:12]:
            location = s(f"  {item['file']}:{item['line']}", "dim")
            print(f"   {s('▸', sev_style)} {item['detail']}{location}")
        if len(items) > 12:
            print(f"   {s(f'... and {len(items) - 12} more', 'dim')}")
        print()

    # Final severity tally
    errors = stats["issues_by_severity"].get("error", 0)
    warnings = stats["issues_by_severity"].get("warning", 0)
    print(f" {s('── Summary ──', 'header', 'bold')}")
    err_str = s(f"❌ Errors:   {errors}", "fail", "bold") if errors else (
        s("  ✅ No errors", "pass", "bold")
    )
    warn_str = s(f"⚠️  Warnings: {warnings}", "warn", "bold") if warnings else (
        s("  ✅ No warnings", "dim")
    )
    print(f"   {err_str}")
    print(f"   {warn_str}")
    total = stats["total_issues"]
    print(f"   {s(f'💡 Total:    {total}', 'info')}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="api_contract_checker.py — Detect frontend-backend API contract mismatches",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python api_contract_checker.py .
  python api_contract_checker.py . --api-prefix /api/v1
  python api_contract_checker.py . --json
  python api_contract_checker.py . --strict
        """,
    )
    parser.add_argument("path", nargs="?", default=".",
                        help="Project root path to scan")
    parser.add_argument("--api-prefix", "-p", default="/api",
                        help="API prefix for backend routes (default: /api)")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--strict", "-s", action="store_true",
                        help="Exit with code 2 on warnings, 1 on errors")
    parser.add_argument("--version", action="version",
                        version="api_contract_checker.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    print(
        f"\n{style('✦', 'header', 'bold')} "
        f"{style('API Contract Checker v1.0.0', 'header')} "
        f"{style(f'— scanning {target}', 'dim')}"
    )

    frontend_calls = scan_frontend_files(target, args.api_prefix)
    backend_routes = scan_backend_files(target, args.api_prefix)

    print(f"   {style('Frontend API calls:', 'info')} {len(frontend_calls)}")
    print(f"   {style('Backend route handlers:', 'info')} {len(backend_routes)}")

    result = analyze_contracts(frontend_calls, backend_routes)

    if args.json:
        # Make issues_by_type serializable
        result["stats"]["issues_by_type"] = dict(result["stats"]["issues_by_type"])
        result["stats"]["issues_by_severity"] = dict(result["stats"]["issues_by_severity"])
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result)

    # Exit codes: 0 = clean, 1 = errors, 2 = warnings only / strict
    issue_count = result["stats"]["total_issues"]
    error_count = result["stats"]["issues_by_severity"].get("error", 0)
    warning_count = result["stats"]["issues_by_severity"].get("warning", 0)

    if error_count > 0:
        sys.exit(1)
    if args.strict and warning_count > 0:
        sys.exit(2)
    if not args.strict and warning_count > 0:
        # Default: warnings are informational, don't fail
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
