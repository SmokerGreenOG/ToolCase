#!/usr/bin/env python3
"""
fake_ui_detector.py — Detect fake/demo UIs with no real backend or core logic.

Identifies indicators that a frontend app is just a mock, prototype, or demo
without real functionality:
  - Hardcoded/mock data files (data.json, sample.js, mock-*.ts)
  - Mock project tree (mocks/, __mocks__/, fixtures/)
  - Demo responses (responses that say "demo", "example", "placeholder")
  - Fake terminal output (console.log with demo markers)
  - Placeholder routes (/demo, /placeholder, /sandbox, /playground)
  - TODO backend calls (fetch/axios calls that end with placeholders)
  - Dummy onClick handlers (onClick that only logs, alerts, or toggles preview)
  - Buttons without real action (disabled or onClick does nothing substantial)
  - Static JSON data presented as real data (constants imported as "data")

Usage:
    python fake_ui_detector.py <path>
    python fake_ui_detector.py <path> --json
    python fake_ui_detector.py <path> --threshold 0.6
    python fake_ui_detector.py <path> --verbose
"""

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = frozenset({
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    "build", "dist", ".next", "out", "coverage", ".vscode", ".idea",
        ".backups",

        ".rsi_backups",

        ".rsi_reports",

        ".self_improve_reports",
        })

FRONTEND_EXTENSIONS = frozenset({
    ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".html", ".css",
    ".scss", ".less", ".json", ".yml", ".yaml",
})

# Patterns that identify fake/demo indicators

# Files that are mock-data or fixture names
MOCK_FILE_PATTERNS = re.compile(
    r'^(mock|fake|stub|sample|dummy|demo|test-data|fixture)[._-]',
    re.IGNORECASE,
)

MOCK_FILE_SUFFIXES = re.compile(
    r'[._-](mock|fake|stub|sample|dummy|demo|fixture|placeholder)s?\.',
    re.IGNORECASE,
)

# Directories that suggest mock/fake structure
MOCK_DIR_NAMES = frozenset({
    "mocks", "__mocks__", "fixtures", "stubs", "fake", "mock-data",
    "test-fixtures", "demo", "dummy", "sample-data",
})

# Route patterns with demo/placeholder names
PLACEHOLDER_ROUTE = re.compile(
    r'(?:path|to|href|route|link)\s*[:=]\s*[\'"](/?(?:demo|placeholder|'
    r'sandbox|playground|sample|mock|stub|example|test-page|fake|'
    r'temp|wip|coming-soon|under-construction|preview))[\'"]',
    re.IGNORECASE,
)

# onClick handlers that are no-ops or purely cosmetic
DUMMY_CLICK = re.compile(
    r'onClick\s*=\s*\{?\s*(?:\(\s*\)\s*=>\s*\{?\s*(?:'
    r'console\.(?:log|warn|debug)\s*\([^)]*\)'
    r'|alert\s*\([^)]*\)'
    r'|void\s*0'
    r'|return\s*;?\s*'
    r'|[a-zA-Z_]\w*\s*&&\s*(?:console\.log|alert)\s*\([^)]*\)'
    r'|set\w+\s*\([^)]*\)'
    r'|toggle\w*\s*\([^)]*\)'
    r'|handle\w*\s*\([^)]*\)'
    r'|preview\w*\s*\([^)]*\)'
    r'))\s*\}?\s*\}',
    re.IGNORECASE,
)

# Disabled / no-action buttons
DISABLED_BUTTON = re.compile(
    r'<(?:button|Button)\b[^>]*disabled\b',
    re.IGNORECASE,
)

NOOP_BUTTON = re.compile(
    r'<(?:button|Button)\b[^>]*(?:'
    r'onClick\s*=\s*\{?\s*(?:undefined|null|console\.log|'
    r'\(\s*\)\s*=>\s*\{?\s*\}?\s*|void\s*0)\s*\}?\s*'
    r')',
    re.IGNORECASE,
)

# Demo/mock response patterns in code comments, console.log, variables
DEMO_MARKER = re.compile(
    r'(?:'
    r'(?://|#|<!--|/\*)\s*(?:TODO|FIXME|HACK|XXX|DEMO|MOCK|FAKE|STUB):?\s*'
    r'|'
    r'console\.(?:log|warn|debug)\s*\(\s*[\'"][^\'"]*'
    r'(?:demo|mock|fake|placeholder|stub|sample|dummy|simulated)'
    r'[\'"]\s*\)'
    r'|'
    r'[\'"][^\'"]*'
    r'(?:demo|mock|fake|placeholder|stub|sample|dummy)-?(?:data|response|api|endpoint|route|handler)'
    r'[\'"]\s*[:=]'
    r')',
    re.IGNORECASE,
)

# API calls using mock/demo URLs
MOCK_API_CALL = re.compile(
    r'(?:fetch|axios|get|post|put|delete|patch|request)\s*'
    r'\(\s*[\'\"](?:https?://)?[^\'"]*'
    r'(?:mock|fake|demo|placeholder|stub|jsonplaceholder|reqres|'
    r'httpbin|mockapi|local-json|test-api|dummyapi)[^\'"]*[\'\"]',
    re.IGNORECASE,
)

# Static JSON imported as data (suggests fake data instead of real API)
STATIC_DATA_IMPORT = re.compile(
    r'(?:import|require)\s+(?:\{?\s*\w+\s*,?\s*\}?\s+from\s+)?'
    r'[\'\"](?:\.\/)?(?:data|sample|mock|fixture|static|dummy)[^\'"]*\.json[\'\"]',
    re.IGNORECASE,
)

# Export of hardcoded mock data arrays/objects used as API responses
HARDCODED_DATA_EXPORT = re.compile(
    r'(?:export\s+(?:const|let|var|function|default)\s+|module\.exports\s*=)'
    r'[^;]*'
    r'(?:mock|fake|demo|sample|dummy|stub|fixture)',
    re.IGNORECASE,
)

# Check for placeholders / stubs in backend calls
TODO_BACKEND_CALL = re.compile(
    r'(?:'
    r'(?://|#|<!--|/\*)\s*TODO\s*:?\s*(?:connect|implement|add|replace)\s*(?:to|with|the)?\s*(?:backend|api|real|actual)\s*'
    r'|'
    r'(?:fetch|axios|get|post)\s*\(\s*[\'\"][^\'"]*'
    r'(?:TODO|PLACEHOLDER|FIXME|CHANGE_ME|YOUR_ENDPOINT)'
    r'[\'"]\s*\)'
    r')',
    re.IGNORECASE,
)

# ===========================================================================
# Detection logic
# ===========================================================================


def is_frontend_file(path: Path) -> bool:
    """Check if a file is a frontend source file we should scan."""
    return path.suffix in FRONTEND_EXTENSIONS and not any(
        part.startswith(".") and part not in (".gitignore",) for part in path.parts
    )


def should_skip_dir(name: str) -> bool:
    """Check if a directory should be excluded from scanning."""
    return name in EXCLUDE_DIRS


def scan_mock_files(root: Path) -> list[dict]:
    """Find files with mock/fake/demo names suggesting they hold fake data."""
    findings = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if MOCK_FILE_PATTERNS.match(path.stem) or MOCK_FILE_SUFFIXES.search(str(path)):
            try:
                rel = path.relative_to(root)
            except ValueError:
                rel = path
            findings.append({
                "file": str(rel),
                "kind": "mock_named_file",
                "category": "Hardcoded data files",
                "detail": f"Filename suggests mock/hardcoded data: {path.name}",
            })
    return findings


def scan_mock_directories(root: Path) -> list[dict]:
    """Find directories with mock/fake names."""
    findings = []
    for path in root.rglob("*"):
        if not path.is_dir():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.name in MOCK_DIR_NAMES:
            try:
                rel = path.relative_to(root)
            except ValueError:
                rel = path
            findings.append({
                "file": str(rel),
                "kind": "mock_directory",
                "category": "Mock project tree",
                "detail": f"Mock/fixture directory present: {path.name}",
            })
    return findings


def scan_placeholder_routes(content: str, filepath: str) -> list[dict]:
    """Scan file content for placeholder route definitions."""
    findings = []
    for match in PLACEHOLDER_ROUTE.finditer(content):
        findings.append({
            "file": filepath,
            "kind": "placeholder_route",
            "category": "Placeholder routes",
            "detail": f"Placeholder route path: {match.group(1)}",
            "line": content[:match.start()].count("\n") + 1,
        })
    return findings


def scan_dummy_onclick(content: str, filepath: str) -> list[dict]:
    """Scan for onClick handlers that do nothing real."""
    findings = []
    for match in DUMMY_CLICK.finditer(content):
        findings.append({
            "file": filepath,
            "kind": "dummy_onclick",
            "category": "Dummy onClick handlers",
            "detail": "onClick handler is a no-op or purely cosmetic",
            "line": content[:match.start()].count("\n") + 1,
        })
    return findings


def scan_disabled_buttons(content: str, filepath: str) -> list[dict]:
    """Scan for disabled buttons or buttons with no real action."""
    findings = []
    for match in DISABLED_BUTTON.finditer(content):
        findings.append({
            "file": filepath,
            "kind": "disabled_button",
            "category": "Buttons without real action",
            "detail": "Button is disabled (no action possible)",
            "line": content[:match.start()].count("\n") + 1,
        })
    for match in NOOP_BUTTON.finditer(content):
        findings.append({
            "file": filepath,
            "kind": "noop_button",
            "category": "Buttons without real action",
            "detail": "Button onClick is undefined, null, or a no-op",
            "line": content[:match.start()].count("\n") + 1,
        })
    return findings


def scan_demo_markers(content: str, filepath: str) -> list[dict]:
    """Scan for demo/mock markers in comments and console.log statements."""
    findings = []
    for match in DEMO_MARKER.finditer(content):
        findings.append({
            "file": filepath,
            "kind": "demo_marker",
            "category": "Demo responses / markers",
            "detail": match.group(0)[:120].strip(),
            "line": content[:match.start()].count("\n") + 1,
        })
    return findings


def scan_mock_api_calls(content: str, filepath: str) -> list[dict]:
    """Scan for API calls pointing to mock/demo endpoints."""
    findings = []
    for match in MOCK_API_CALL.finditer(content):
        findings.append({
            "file": filepath,
            "kind": "mock_api_call",
            "category": "Demo responses",
            "detail": f"Mock API endpoint call: {match.group(0)[:110].strip()}",
            "line": content[:match.start()].count("\n") + 1,
        })
    return findings


def scan_static_json_data(content: str, filepath: str) -> list[dict]:
    """Scan for static JSON imported as live data source."""
    findings = []
    for match in STATIC_DATA_IMPORT.finditer(content):
        findings.append({
            "file": filepath,
            "kind": "static_json_data",
            "category": "Static JSON shown as real data",
            "detail": f"Static/mock JSON imported as data: {match.group(0)[:110].strip()}",
            "line": content[:match.start()].count("\n") + 1,
        })
    for match in HARDCODED_DATA_EXPORT.finditer(content):
        findings.append({
            "file": filepath,
            "kind": "hardcoded_mock_export",
            "category": "Static JSON shown as real data",
            "detail": f"Hardcoded mock data export: {match.group(0)[:120].strip()}",
            "line": content[:match.start()].count("\n") + 1,
        })
    return findings


def scan_todo_backend_calls(content: str, filepath: str) -> list[dict]:
    """Scan for TODO comments or placeholder URLs indicating backend not connected."""
    findings = []
    for match in TODO_BACKEND_CALL.finditer(content):
        findings.append({
            "file": filepath,
            "kind": "todo_backend_call",
            "category": "TODO backend calls",
            "detail": match.group(0)[:130].strip(),
            "line": content[:match.start()].count("\n") + 1,
        })
    return findings


def scan_fake_terminal_output(content: str, filepath: str) -> list[dict]:
    """Scan for fake/simulated terminal output in code (log messages, test output)."""
    findings = []
    # Patterns that indicate simulated terminal/log output
    fake_terminal_pattern = re.compile(
        r'(?:'
        r'console\.(?:log|warn|debug)\s*\(\s*[\'"]'
        r'\[(?:DEMO|MOCK|SIMULATED|FAKE|PREVIEW|DEV|SANDBOX)\]'
        r'|'
        r'(?://|#|<!--)\s*(?:SIMULATED|FAKE|MOCK)\s+'
        r'(?:OUTPUT|RESPONSE|TERMINAL|CONSOLE|LOG)'
        r')',
        re.IGNORECASE,
    )
    for match in fake_terminal_pattern.finditer(content):
        findings.append({
            "file": filepath,
            "kind": "fake_terminal_output",
            "category": "Fake terminal output",
            "detail": f"Simulated terminal/log output: {match.group(0)[:110].strip()}",
            "line": content[:match.start()].count("\n") + 1,
        })
    return findings


# ===========================================================================
# Aggregation and scoring
# ===========================================================================

CATEGORY_WEIGHTS = {
    "Hardcoded data files": 0.10,
    "Mock project tree": 0.10,
    "Demo responses / markers": 0.12,
    "Fake terminal output": 0.15,
    "Placeholder routes": 0.12,
    "TODO backend calls": 0.15,
    "Dummy onClick handlers": 0.10,
    "Buttons without real action": 0.08,
    "Static JSON shown as real data": 0.08,
}


def compute_fake_score(findings: list[dict]) -> float:
    """Compute a 0.0–1.0 fake/demo UI likelihood score."""
    if not findings:
        return 0.0

    # Group by category
    cat_counts = defaultdict(int)
    for f in findings:
        cat_counts[f["category"]] += 1

    # Weighted score per category (capped at 1.0 per category)
    score = 0.0
    for cat, weight in CATEGORY_WEIGHTS.items():
        count = cat_counts.get(cat, 0)
        if count > 0:
            # Each finding adds weight, up to a max of the full weight of that category
            category_score = min(count * weight, weight)
            score += category_score

    return min(score, 1.0)


def get_severity(score: float) -> str:
    """Return a label for the fake/demo likelihood score."""
    if score >= 0.8:
        return "CRITICAL"
    elif score >= 0.5:
        return "HIGH"
    elif score >= 0.3:
        return "MEDIUM"
    elif score >= 0.1:
        return "LOW"
    return "NONE"


# ===========================================================================
# Scanning
# ===========================================================================


def collect_source_files(root: Path) -> list[Path]:
    """Collect all frontend source files from the project directory."""
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if is_frontend_file(path):
            files.append(path)
    return files


def scan_project(root: Path, verbose: bool = False) -> dict:
    """Run all fake-UI detection scans on the project."""
    findings = []

    # Structural scans (filesystem-based)
    if verbose:
        print(f"  Scanning for mock-named files...", file=sys.stderr)
    findings.extend(scan_mock_files(root))

    if verbose:
        print(f"  Scanning for mock directories...", file=sys.stderr)
    findings.extend(scan_mock_directories(root))

    # Content scans (parse each file)
    files = collect_source_files(root)
    if verbose:
        print(f"  Scanning {len(files)} frontend source files...", file=sys.stderr)

    for fp in files:
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue

        try:
            rel_path = str(fp.relative_to(root))
        except ValueError:
            rel_path = str(fp)

        findings.extend(scan_placeholder_routes(content, rel_path))
        findings.extend(scan_dummy_onclick(content, rel_path))
        findings.extend(scan_disabled_buttons(content, rel_path))
        findings.extend(scan_demo_markers(content, rel_path))
        findings.extend(scan_mock_api_calls(content, rel_path))
        findings.extend(scan_static_json_data(content, rel_path))
        findings.extend(scan_todo_backend_calls(content, rel_path))
        findings.extend(scan_fake_terminal_output(content, rel_path))

    score = compute_fake_score(findings)
    counts = defaultdict(int)
    for f in findings:
        counts[f["category"]] += 1

    return {
        "score": round(score, 3),
        "severity": get_severity(score),
        "total_findings": len(findings),
        "categories": dict(counts),
        "findings": findings,
    }


# ===========================================================================
# Reporting
# ===========================================================================


def print_report(result: dict, root: Path, verbose: bool = False) -> None:
    """Print a human-readable report of fake/demo UI indicators."""
    score = result["score"]
    severity = result["severity"]
    total = result["total_findings"]
    categories = result["categories"]
    findings = result["findings"]

    # Severity colors (ASCII)
    sev_color = {
        "CRITICAL": "\033[91m",  # red
        "HIGH": "\033[93m",      # yellow
        "MEDIUM": "\033[96m",    # cyan
        "LOW": "\033[94m",       # blue
        "NONE": "\033[92m",      # green
    }.get(severity, "")

    print(f"\n{'='*70}")
    print(f"  🔍 Fake UI Detector — scanning {root}")
    print(f"{'='*70}")
    print(f"  Fake/demo score: {sev_color}{score:.1%}\033[0m  ({severity})")
    print(f"  Total indicators found: {total}")
    print()

    if not findings:
        print("  ✅ No fake/demo UI indicators detected.")
        print()
        return

    print(f"  ── Breakdown by Category ──")
    for cat, weight in sorted(CATEGORY_WEIGHTS.items(), key=lambda x: x[1], reverse=True):
        count = categories.get(cat, 0)
        bar = "█" * min(count, 20) + "░" * max(0, 20 - min(count, 20))
        print(f"   {bar}  {cat}: {count}")
    print()

    # Group findings by category for detailed output
    grouped = defaultdict(list)
    for f in findings:
        grouped[f["category"]].append(f)

    for category, items in grouped.items():
        print(f"  ── {category} ({len(items)}) ──")
        # Show at most 8 items per category (or more in verbose mode)
        limit = 15 if verbose else 8
        for item in items[:limit]:
            line_info = f" (line {item['line']})" if "line" in item else ""
            print(f"     • {item['detail']}{line_info}")
        if len(items) > limit:
            print(f"     ... and {len(items) - limit} more")
        print()

    # Recommendations
    print(f"  ── Recommendations ──")
    recommendations = []
    if score >= 0.5:
        recommendations.append(
            "  🔴 Replace mock data files with real API endpoints or dynamic data sources."
        )
    if categories.get("TODO backend calls", 0) > 0:
        recommendations.append(
            "  🔴 Implement real backend connections for TODO-marked API calls."
        )
    if categories.get("Placeholder routes", 0) > 0:
        recommendations.append(
            "  🟡 Remove or replace placeholder/demo routes with real content."
        )
    if categories.get("Dummy onClick handlers", 0) > 0:
        recommendations.append(
            "  🟡 Replace dummy onClick handlers with real business logic."
        )
    if categories.get("Static JSON shown as real data", 0) > 0:
        recommendations.append(
            "  🟡 Serve data from real APIs instead of importing static JSON as data."
        )
    if categories.get("Mock project tree", 0) > 0:
        recommendations.append(
            "  🟢 Clean up mock/fixture directories if no longer needed."
        )
    if categories.get("Buttons without real action", 0) > 0:
        recommendations.append(
            "  🟢 Wire up disabled/no-op buttons or remove them from production."
        )

    for rec in recommendations:
        print(rec)
    print()


# ===========================================================================
# CLI
# ===========================================================================


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="fake_ui_detector.py — Detect fake/demo UIs with no real backend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python fake_ui_detector.py .
  python fake_ui_detector.py src/ --json
  python fake_ui_detector.py . --threshold 0.6
  python fake_ui_detector.py . --verbose
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root to scan")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument("--threshold", "-t", type=float, default=0.0,
                        help="Minimum score threshold to exit with code 1 (default: 0.0)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show per-file scanning progress")
    parser.add_argument("--version", action="version",
                        version="fake_ui_detector.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    result = scan_project(target, verbose=args.verbose)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result, target, verbose=args.verbose)

    # Exit code: 0 if below threshold, 1 if at or above
    if result["score"] >= args.threshold and args.threshold > 0:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
