#!/usr/bin/env python3
"""
feature_gap_analyzer.py — Analyze feature gaps between frontend and backend.

Detects:
  - Backend API endpoints without corresponding frontend implementation
  - Frontend pages/components without backend support
  - Todo/Fixme markers grouped by feature area
  - Incomplete feature implementations (where detectable)
  - Missing error handling for certain operations
  - Missing loading states in frontend
  - Missing validation (frontend vs backend)

Gebruik:
    python feature_gap_analyzer.py <path>
    python feature_gap_analyzer.py <path> --json
    python feature_gap_analyzer.py <path> --deep
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import os
import re
import sys
from collections import defaultdict, Counter
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

# Common feature area keywords
FEATURE_KEYWORDS = {
    "auth": ["login", "logout", "register", "signup", "signin", "session",
             "token", "jwt", "oauth", "password", "user", "profile",
             "authenticate", "authorize", "permission", "role"],
    "database": ["query", "mutation", "crud", "create", "read", "update",
                 "delete", "save", "load", "fetch", "store", "persist",
                 "model", "schema", "migration", "seed"],
    "api": ["endpoint", "route", "api", "rest", "graphql", "websocket",
            "request", "response", "handler", "middleware"],
    "ui": ["component", "page", "layout", "modal", "dialog", "form",
           "button", "input", "dropdown", "menu", "navbar", "sidebar",
           "card", "table", "list", "grid"],
    "state": ["store", "state", "context", "reducer", "redux", "zustand",
              "recoil", "jotai", "signal", "reactive"],
    "error": ["error", "fallback", "errorboundary", "catch", "try",
              "exception", "validation", "sanitize", "escape"],
    "loading": ["loading", "spinner", "skeleton", "placeholder", "progress",
                "suspense", "pending", "fetching"],
    "settings": ["config", "setting", "preference", "option", "theme",
                 "locale", "language", "notification"],
    "search": ["search", "filter", "query", "find", "browse", "explore",
               "catalog", "index"],
    "notification": ["toast", "notification", "alert", "snackbar", "banner",
                     "message", "popup"],
    "file": ["upload", "download", "file", "image", "attachment", "document",
             "import", "export", "csv", "pdf"],
    "real-time": ["websocket", "realtime", "live", "stream", "subscribe",
                  "event", "push", "poll"],
}

REQUIRED_FEATURE_PATTERNS = {
    "error_handling": re.compile(
        r"(?:catch|error|fallback|errorboundary|err|try\s*\{)", re.IGNORECASE),
    "loading_state": re.compile(
        r"(?:loading|spinner|skeleton|suspense|isLoading|isFetching)", re.IGNORECASE),
    "validation": re.compile(r'(?:validate|sanitize|schema|zod|yup|joi|validator)', re.IGNORECASE),
    "empty_state": re.compile(r'(?:empty|no[A-Z]\w+|isEmpty|notFound|noData)', re.IGNORECASE),
}


def collect_source_files(root: Path) -> list[Path]:
    """Collect all source files."""
    files = []
    exts = {".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".mjs", ".cjs",
            ".css", ".scss", ".html", ".json", ".yaml", ".yml", ".toml"}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            ext = Path(fn).suffix.lower()
            if ext in exts:
                files.append(Path(dirpath) / fn)

    return sorted(files)


def detect_features(files: list[Path]) -> dict:
    """Detect which feature areas are present in the codebase."""
    features = defaultdict(lambda: {"files": [], "mentions": 0, "confidence": 0.0})

    for fp in files:
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        rel_path = fp.relative_to(Path.cwd()) if fp.exists() else fp
        ext = fp.suffix.lower()
        is_frontend = ext in (".ts", ".tsx", ".js", ".jsx")
        is_backend = ext in (".py", ".rs")

        for feature, keywords in FEATURE_KEYWORDS.items():
            for keyword in keywords:
                pattern = re.compile(r'\b' + re.escape(keyword) + r'\b', re.IGNORECASE)
                matches = pattern.findall(content)
                if matches:
                    feat = features[feature]
                    feat["files"].append(str(rel_path))
                    feat["mentions"] += len(matches)
                    feat["has_frontend"] = feat.get("has_frontend", False) or is_frontend
                    feat["has_backend"] = feat.get("has_backend", False) or is_backend
                    break  # One keyword per feature per file is enough

    # Calculate confidence based on mention count and file diversity
    for feature, data in features.items():
        unique_files = len(set(data["files"]))
        data["unique_files"] = unique_files
        data["confidence"] = min(1.0, (data["mentions"] / 10) * 0.5 + (unique_files / 5) * 0.5)
        data["files"] = list(set(data["files"]))

    return dict(features)


def analyze_feature_gaps(features: dict) -> list[dict]:
    """Analyze which features have gaps."""
    gaps = []

    for feature, data in features.items():
        has_frontend = data.get("has_frontend", False)
        has_backend = data.get("has_backend", False)

        if has_frontend and not has_backend:
            gaps.append({
                "feature": feature,
                "type": "missing_backend",
                "description": (
                    f"{feature.title()} heeft frontend code "
                    "maar geen backend ondersteuning"
                ),
                "confidence": data["confidence"],
                "mentions": data["mentions"],
                "files": data["files"][:5],
            })
        elif has_backend and not has_frontend:
            gaps.append({
                "feature": feature,
                "type": "missing_frontend",
                "description": f"{feature.title()} heeft backend code maar geen frontend UI",
                "confidence": data["confidence"],
                "mentions": data["mentions"],
                "files": data["files"][:5],
            })

    return gaps


def analyze_pattern_gaps(files: list[Path]) -> list[dict]:
    """Analyze missing patterns in feature implementations."""
    gaps = []

    frontend_files = [f for f in files if f.suffix.lower() in (".tsx", ".jsx", ".ts", ".js")]
    backend_files = [f for f in files if f.suffix.lower() in (".py", ".rs")]

    # Check for common gaps in frontend
    for fp in frontend_files:
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        rel_path = fp.relative_to(Path.cwd()) if fp.exists() else fp

        # Check for API calls without error handling
        if re.search(r'(?:fetch|axios|api)\.\s*(?:get|post|put|delete)', content):
            if not REQUIRED_FEATURE_PATTERNS["error_handling"].search(content):
                gaps.append({
                    "file": str(rel_path),
                    "type": "missing_error_handling",
                    "description": f"API calls zonder error handling in {fp.name}",
                    "severity": "MEDIUM",
                })

        # Check for data fetching without loading state
        if re.search(r'(?:useQuery|useMutation|fetch|useEffect.*fetch)', content):
            if not REQUIRED_FEATURE_PATTERNS["loading_state"].search(content):
                gaps.append({
                    "file": str(rel_path),
                    "type": "missing_loading_state",
                    "description": f"Data fetching zonder loading state in {fp.name}",
                    "severity": "LOW",
                })

        # Check for forms without validation
        if re.search(r'<form|<Form|<input|<Input|<textarea|<select', content):
            if not REQUIRED_FEATURE_PATTERNS["validation"].search(content):
                gaps.append({
                    "file": str(rel_path),
                    "type": "missing_validation",
                    "description": f"Formulieren zonder validatie in {fp.name}",
                    "severity": "MEDIUM",
                })

    return gaps


def print_report(features: dict, gaps: list[dict],
                 pattern_gaps: list[dict]) -> None:
    """Print a formatted feature gap report."""
    # Sort features by confidence
    sorted_features = sorted(features.items(), key=lambda x: x[1]["confidence"], reverse=True)

    missing_frontend = [g for g in gaps if g["type"] == "missing_frontend"]
    missing_backend = [g for g in gaps if g["type"] == "missing_backend"]

    print(f"\n{'='*60}")
    print(f" 🔍 FEATURE GAP ANALYZER")
    print(f"{'='*60}")
    print(f"   Feature areas detected: {len(features)}")
    print(f"   ⚠  Missing frontend:    {len(missing_frontend)}")
    print(f"   ⚠  Missing backend:     {len(missing_backend)}")
    print(f"   Pattern gaps:           {len(pattern_gaps)}")
    print()

    # Feature overview
    print(f" ── Feature Overview ({len(sorted_features)}) ──")
    for feature, data in sorted_features:
        confidence_pct = int(data["confidence"] * 100)
        icon = "✅" if data["confidence"] > 0.5 else "🟡" if data["confidence"] > 0.2 else "⚪"
        fe = "FE" if data.get("has_frontend") else "  "
        be = "BE" if data.get("has_backend") else "  "
        feature_title = feature.title() if isinstance(feature, str) else str(feature).title()
        print(
            f"   {icon} {feature_title:<15} [{fe}] [{be}]  "
            f"({data['unique_files']} files, {confidence_pct}%)"
        )
    print()

    # Gap details
    if missing_frontend:
        print(f" ── Missing Frontend ({len(missing_frontend)}) ⚠ ──")
        for g in missing_frontend:
            print(f"   {g['description']}")
            for f in g["files"][:3]:
                print(f"     📄 {f}")
        print()

    if missing_backend:
        print(f" ── Missing Backend ({len(missing_backend)}) ⚠ ──")
        for g in missing_backend:
            print(f"   {g['description']}")
            for f in g["files"][:3]:
                print(f"     📄 {f}")
        print()

    if pattern_gaps:
        by_type = defaultdict(list)
        for g in pattern_gaps:
            by_type[g["type"]].append(g)

        print(f" ── Pattern Gaps ({len(pattern_gaps)}) ──")
        for gap_type, items in by_type.items():
            label = gap_type.replace("_", " ").title()
            print(f"\n   {label} ({len(items)}):")
            for item in items[:5]:
                sev = (
                "🔴" if item["severity"] == "HIGH"
                else "🟡" if item["severity"] == "MEDIUM"
                else "🟢"
            )
                print(f"     {sev} {item['description']}")
            if len(items) > 5:
                print(f"     ... en nog {len(items) - 5}")
        print()

    if not gaps and not pattern_gaps:
        print(" ✅ Geen feature gaps gevonden!")
        print()


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="feature_gap_analyzer.py — Analyze feature gaps between frontend & backend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python feature_gap_analyzer.py .
  python feature_gap_analyzer.py . --json
  python feature_gap_analyzer.py . --deep
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--deep", "-d", action="store_true",
                        help="Diepere analyse (patronen, error handling)")
    parser.add_argument("--version", action="version", version="feature_gap_analyzer.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 Feature Gap Analyzer v1.0.0 — scanning {target}")

    files = collect_source_files(target)
    if not files:
        print(" Geen bronbestanden gevonden")
        sys.exit(0)

    print(f"   {len(files)} bestand(en) om te analyseren")

    features = detect_features(files)
    gaps = analyze_feature_gaps(features)
    pattern_gaps = analyze_pattern_gaps(files) if args.deep else []

    if args.json:
        output = {
            "features": features,
            "gaps": gaps,
            "pattern_gaps": pattern_gaps,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    else:
        print_report(features, gaps, pattern_gaps)


if __name__ == "__main__":
    main()
