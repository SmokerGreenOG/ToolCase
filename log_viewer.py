#!/usr/bin/env python3
"""
log_viewer.py — Scan and summarize errors in project log files.

Detects:
  - Log files in logs/ directory
  - *.log files anywhere in the project
  - npm-debug.log, yarn-error.log, pnpm-debug.log
  - Python tracebacks
  - Backend server errors (500, 4xx, unhandled exceptions)
  - Frontend console errors
  - Crash reports and core dumps

Output per error category:
  - Last error (most recent timestamp)
  - Most frequent error
  - Possible cause
  - File where the error occurs
  - Recommended fix

Usage:
    python log_viewer.py <path>
    python log_viewer.py <path> --json
    python log_viewer.py <path> --since "2025-01-01"
    python log_viewer.py <path> --type error,warn
"""

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = frozenset({
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    ".tox", ".eggs", "build", "dist", ".next", ".husky/_",
    ".git2", ".svn", ".hg", ".idea", ".vscode",
        ".backups",
        
        ".rsi_backups",
        
        ".rsi_reports",
        
        ".self_improve_reports",
        })

LOG_EXTENSIONS = {".log", ".out", ".err"}

NAMED_LOG_FILES = frozenset({
    "npm-debug.log",
    "yarn-error.log",
    "pnpm-debug.log",
    "yarn-debug.log",
    "lerna-debug.log",
    "bootstrap.log",
    "install.log",
    "error.log",
    "access.log",
    "debug.log",
    "crash.log",
    "crashreport.log",
    "crash-",  # prefix match
})

CRASH_FILE_PATTERNS = [
    re.compile(r"crash", re.IGNORECASE),
    re.compile(r"hs_err_pid\d+", re.IGNORECASE),
    re.compile(r"core\.\d+"),
    re.compile(r"\.dmp$", re.IGNORECASE),
    re.compile(r"\.mdmp$", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Error pattern definitions
# ---------------------------------------------------------------------------


class ErrorPattern:
    """Describes a type of error to detect in log files."""

    def __init__(self, name: str, category: str, patterns: list[str],
                 cause_template: str, fix_template: str):
        self.name = name
        self.category = category
        self.compiled = [re.compile(p, re.MULTILINE | re.DOTALL) for p in patterns]
        self.cause_template = cause_template
        self.fix_template = fix_template

    def match(self, text: str, file_path: Path) -> list[dict]:
        """Find all matches in text, returning dicts with line and context."""
        results = []
        for cp in self.compiled:
            for m in cp.finditer(text):
                # Determine line number
                line_num = text[:m.start()].count("\n") + 1
                # Extract context (the matched text, truncated)
                matched = m.group(0).strip()
                if len(matched) > 300:
                    matched = matched[:300] + "..."
                results.append({
                    "pattern": self.name,
                    "category": self.category,
                    "line": line_num,
                    "match": matched,
                    "file": str(file_path),
                    "cause": self.cause_template,
                    "fix": self.fix_template,
                })
        return results


# ---------------------------------------------------------------------------
# Error pattern definitions
# ---------------------------------------------------------------------------

ERROR_PATTERNS = [
    # Python tracebacks
    ErrorPattern(
        name="Python Traceback",
        category="python",
        patterns=[
            r"Traceback \(most recent call last\):\n(?:  File .+\n)*\w+(?:Error|Exception|Warning|Interrupt).+",
            r"Traceback \(most recent call last\):.*?(?=\n\n|\Z)",
        ],
        cause_template=("Unhandled Python exception — missing try/except or unexpected runtime"
               "condition"),
        fix_template=("Add proper exception handling or fix the root cause at the line indicated in the"
               "traceback"),
    ),

    # 500 Internal Server Error
    ErrorPattern(
        name="HTTP 500 Error",
        category="backend",
        patterns=[
            r"(?:HTTP|Status|Response).*?[5]\d{2}",
            r"500.*?(?:Internal Server Error|error|fail)",
            r"(?:Internal Server Error|internal server error)",
            r"GET|POST|PUT|DELETE|PATCH .*? 500",
        ],
        cause_template="Unhandled server-side exception during request processing",
        fix_template=("Check server logs for the traceback preceding the 500; add error handling in the failing"
               "route handler"),
    ),

    # 4xx Client Errors
    ErrorPattern(
        name="HTTP 4xx Error",
        category="backend",
        patterns=[
            r"(?:HTTP|Status|Response).*?[4]\d{2}",
            r"404.*?(?:Not Found|error|fail)",
            r"403.*?(?:Forbidden|error|fail)",
            r"401.*?(?:Unauthorized|error|fail)",
            r"400.*?(?:Bad Request|error|fail)",
            r"GET|POST|PUT|DELETE|PATCH .*? 4\d{2}",
        ],
        cause_template=("Client error — invalid request, missing resource, or authentication"
               "failure"),
        fix_template="Check the requested URL, authentication headers, and request body format",
    ),

    # Backend unhandled exceptions (generic)
    ErrorPattern(
        name="Backend Exception",
        category="backend",
        patterns=[
            r"Unhandled\s+(?:exception|error|rejection)",
            r"uncaughtException",
            r"unhandledRejection",
            r"Segmentation\s+fault",
            r"panic(?:ic)?[!:].*?(?:at |in )",
            r"FATAL[!:].*",
            r"\[fatal\].*",
        ],
        cause_template="Unhandled exception crashing the backend process",
        fix_template=("Wrap the failing code path in a try/catch or error boundary; check for null pointer /"
               "undefined access"),
    ),

    # Node.js / npm errors
    ErrorPattern(
        name="npm/yarn/pnpm Error",
        category="node",
        patterns=[
            r"npm\s+ERR(?:OR)?[!:].*",
            r"ERR\s*\!.*",
            r"error\s+(?:while\s+)?(?:running|executing|installing|resolving)",
            r"Module\s+not\s+found",
            r"Cannot\s+find\s+module",
            r"resolution\s+failed",
            r"ETARGET|E404|EINTEGRITY|EACCES|EPERM|ENOENT|ENOTDIR",
        ],
        cause_template=("Package manager error — missing module, version conflict, or permission"
               "issue"),
        fix_template=("Delete node_modules and reinstall (rm -rf node_modules && npm install), or fix the"
               "package.json dependency versions"),
    ),

    # Frontend console errors
    ErrorPattern(
        name="Frontend Console Error",
        category="frontend",
        patterns=[
            r"(?:console\s*\.\s*error|console\.warn)\s*\(.*\)",
            r"\[Error\].*",
            r"Uncaught\s+(?:TypeError|ReferenceError|SyntaxError|RangeError)",
            r"Cannot\s+read\s+property\s+['\"]?\w+['\"]?\s+of\s+(?:null|undefined)",
            r"is\s+not\s+(?:defined|a function|an object)",
            r"Failed\s+to\s+(?:load|fetch|parse|compile)",
            r"NetworkError|Network\s+Error",
            r"ChunkLoadError",
        ],
        cause_template="Frontend runtime JavaScript/TypeScript error",
        fix_template=("Check the source map reference in the error; verify API endpoint URLs and data"
               "shapes"),
    ),

    # Database errors
    ErrorPattern(
        name="Database Error",
        category="database",
        patterns=[
            r"(?:SQL|DB|DATABASE|Mongo|MySQL|PostgreSQL|SQLite|Redis)\s+(?:error|ERROR|fail|FAIL|exception)",
            r"Connection\s+(?:refused|reset|timeout|closed|lost|failed)",
            r"Can't\s+connect\s+to",
            r"ECONNREFUSED|ECONNRESET|ETIMEDOUT",
            r"Duplicate\s+entry",
            r"Deadlock\s+found",
            r"Lock\s+wait\s+timeout",
            r"relation\s+['\"]?\w+['\"]?\s+does\s+not\s+exist",
            r"Base\s+table\s+or\s+view\s+not\s+found",
        ],
        cause_template="Database connection failure, query error, or constraint violation",
        fix_template=("Verify database credentials, connection string, and that the database server is running;"
               "check for schema mismatches"),
    ),

    # Docker / Container errors
    ErrorPattern(
        name="Container Error",
        category="infra",
        patterns=[
            r"(?:Docker|container|dockerd)\s+(?:error|ERROR|fail|FAIL|exception)",
            r"Error\s+response\s+from\s+daemon",
            r"Container\s+.*\s+(?:exited|died|crashed)",
            r"OOMKilled|Out\s+of\s+memory",
            r"failed\s+to\s+register\s+layer",
            r"no\s+such\s+image",
            r"port\s+is\s+already\s+allocated",
        ],
        cause_template="Docker container or image issue",
        fix_template=("Check Docker daemon status, free up ports, prune unused images/containers, or increase"
               "memory limits"),
    ),

    # Crash reports
    ErrorPattern(
        name="Crash Report",
        category="crash",
        patterns=[
            r"(?:Crash|Fatal|Panic|Abort)\s*(?:Report|Dump|Log)?[!:].*(?:\n.*){0,10}",
            r"Application\s+Crashed",
            r"SIGSEGV|SIGABRT|SIGBUS|SIGILL|SIGFPE",
            r"Stack\s+Dump[!:].*(?:\n.*){0,20}",
            r"Thread\s+\d+\s+(?:Crashed|received\s+signal)",
        ],
        cause_template=("Application crash — memory corruption, null pointer, or unrecoverable"
               "error"),
        fix_template=("Analyze the stack dump; check for buffer overflows, use-after-free, or null dereferences;"
               "update to latest version"),
    ),

    # Build / Compilation errors
    ErrorPattern(
        name="Build Error",
        category="build",
        patterns=[
            r"BUILD\s+(?:FAILED|ERROR|BROKEN)",
            r"Compilation\s+(?:failed|error)",
            r"Error\s+compiling",
            r"error\[E\d+\]",  # Rust compile errors
            r"TS\d+:",  # TypeScript errors
            r"Module\s+build\s+failed",
            r"Failed\s+to\s+compile",
            r"Build\s+failed\s+with\s+\d+\s+error",
        ],
        cause_template=("Build/compilation error — syntax issue, type mismatch, or missing"
               "dependency"),
        fix_template=("Inspect the build output for specific file/line references and fix the reported"
               "issue"),
    ),

    # Authentication / Authorization errors
    ErrorPattern(
        name="Auth Error",
        category="security",
        patterns=[
            r"(?:Authentication|Authorization|Auth|Login|Token)\s+(?:failed|error|denied|expired|invalid|rejected)",
            r"Invalid\s+(?:API key|token|credential|password|secret)",
            r"Unauthorized|Forbidden|Access\s+Denied",
            r"JWT\s+(?:expired|invalid|malformed)",
            r"Rate\s+limit\s+(?:exceeded|reached)",
        ],
        cause_template="Authentication or authorization failure",
        fix_template=("Check API keys, tokens, and credentials; verify permissions and expiry dates; review rate"
               "limit configuration"),
    ),
]

# Generic timestamp patterns for log lines
TIMESTAMP_PATTERNS = [
    re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"),
    re.compile(r"\d{2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2}"),
    re.compile(r"[A-Z][a-z]{2} [A-Z][a-z]{2} \d{2} \d{2}:\d{2}:\d{2} \d{4}"),
    re.compile(r"\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2}"),
    re.compile(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}"),
    re.compile(r"\d{4}\.\d{2}\.\d{2}"),
]


# ---------------------------------------------------------------------------
# Log file discovery
# ---------------------------------------------------------------------------


def discover_log_files(root: Path) -> list[Path]:
    """Discover all relevant log files in the project."""
    found: list[Path] = []

    # 1. Walk the tree for *.log files and named log files
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        dir_path = Path(dirpath)

        for fn in filenames:
            fp = dir_path / fn
            ext = fp.suffix.lower()

            # Match by extension
            if ext in LOG_EXTENSIONS:
                found.append(fp)
                continue

            # Match by name (exact or prefix)
            if fn in NAMED_LOG_FILES:
                found.append(fp)
                continue

            # Match crash-related files
            for cp in CRASH_FILE_PATTERNS:
                if cp.search(fn):
                    found.append(fp)
                    break

    # 2. Specifically look in logs/ directory even if not traversed
    logs_dir = root / "logs"
    if logs_dir.exists():
        for fn in os.listdir(logs_dir):
            fp = logs_dir / fn
            if fp.is_file() and fp not in found:
                # Accept any file in logs/ that isn't binary-garbage
                try:
                    with open(fp, "rb") as fh:
                        head = fh.read(512)
                    if b"\x00" not in head:  # skip binary
                        found.append(fp)
                except Exception:
                    pass

    # Deduplicate and sort
    seen = set()
    unique = []
    for fp in sorted(found, key=lambda p: (str(p.parent), p.name)):
        s = str(fp.resolve())
        if s not in seen:
            seen.add(s)
            unique.append(fp)

    return unique


# ---------------------------------------------------------------------------
# Error scanning
# ---------------------------------------------------------------------------


def scan_file_for_errors(file_path: Path) -> list[dict]:
    """Scan a single file for all known error patterns."""
    results = []
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        # Try latin-1 as fallback
        try:
            text = file_path.read_text(encoding="latin-1", errors="replace")
        except Exception:
            return results

    for pattern in ERROR_PATTERNS:
        try:
            matches = pattern.match(text, file_path)
            results.extend(matches)
        except Exception:
            continue

    return results


def extract_timestamp(line: str) -> str | None:
    """Extract the first timestamp from a line, returning it as a string."""
    for tp in TIMESTAMP_PATTERNS:
        m = tp.search(line)
        if m:
            return m.group(0)
    return None


def parse_timestamp(ts: str) -> datetime | None:
    """Try to parse a timestamp string into a datetime object."""
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%d/%b/%Y:%H:%M:%S",
        "%d/%b/%Y:%H:%M:%S %z",
        "%a %b %d %H:%M:%S %Y",
        "%d-%m-%Y %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y.%m.%d",
    ]
    for fmt in formats:
        try:
            # Strip timezone info for parsing if needed
            cleaned = ts.strip()
            # Handle +HH:MM or Z suffix
            if cleaned.endswith("Z"):
                cleaned = cleaned[:-1]
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def categorize_and_summarize(errors: list[dict]) -> dict:
    """Group errors by category and produce summary statistics."""
    if not errors:
        return {
            "total_errors": 0,
            "categories": {},
            "summary": "No errors found.",
        }

    # Group by category
    by_category: dict[str, list[dict]] = defaultdict(list)
    for err in errors:
        by_category[err["category"]].append(err)

    categories_output = {}
    total_errors = len(errors)

    for cat, cat_errors in sorted(by_category.items()):
        # Group by specific error name/pattern within category
        by_pattern: dict[str, list[dict]] = defaultdict(list)
        for err in cat_errors:
            by_pattern[err["pattern"]].append(err)

        patterns_output = {}
        for pat_name, pat_errors in sorted(by_pattern.items()):
            # Most frequent error message (exact match text)
            message_counter: Counter = Counter(e["match"] for e in pat_errors)
            most_frequent_msg, freq_count = message_counter.most_common(1)[0]

            # Last error (by file or line number - approximate)
            last_error = pat_errors[-1]

            # Unique files affected
            affected_files = sorted(set(e["file"] for e in pat_errors))

            # Cause and fix (use the one from last error as representative)
            cause = pat_errors[0]["cause"] if pat_errors else "Unknown"
            fix = pat_errors[0]["fix"] if pat_errors else "Investigate manually"

            patterns_output[pat_name] = {
                "count": len(pat_errors),
                "last_error": {
                    "file": last_error["file"],
                    "line": last_error["line"],
                    "message": last_error["match"],
                },
                "most_frequent": {
                    "message": most_frequent_msg,
                    "occurrences": freq_count,
                },
                "affected_files": affected_files,
                "possible_cause": cause,
                "recommended_fix": fix,
            }

        categories_output[cat] = {
            "total": len(cat_errors),
            "patterns": patterns_output,
        }

    # Overall most frequent error
    all_messages: Counter = Counter(e["match"] for e in errors)
    overall_most_frequent_msg, overall_freq_count = all_messages.most_common(1)[0]

    return {
        "total_errors": total_errors,
        "categories": categories_output,
        "summary": {
            "overall_most_frequent_error": overall_most_frequent_msg,
            "overall_most_frequent_count": overall_freq_count,
            "total_files_with_errors": len(set(e["file"] for e in errors)),
            "error_categories_found": sorted(by_category.keys()),
        },
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def print_report(stats: dict, root: Path) -> None:
    """Print a formatted error summary report."""
    total = stats["total_errors"]

    print(f"\n{'='*60}")
    print(f" 📄 LOG VIEWER — Error Summary")
    print(f"{'='*60}")
    print(f"   Scanned path: {root}")
    print(f"   Total errors found: {total}")
    print()

    if total == 0:
        print(" ✅ No errors detected in log files.")
        print()
        return

    # Print summary
    s = stats.get("summary", {})
    print(f" ── Overview ──")
    print(f"   Most frequent error: {s.get('overall_most_frequent_error', 'N/A')[:100]}")
    print(f"   Occurrences: {s.get('overall_most_frequent_count', 0)}")
    print(f"   Files with errors: {s.get('total_files_with_errors', 0)}")
    print(f"   Categories found: {', '.join(s.get('error_categories_found', []))}")
    print()

    # Per category
    for cat_name, cat_data in sorted(stats.get("categories", {}).items()):
        category_labels = {
            "python": "🐍 Python Errors",
            "backend": "⚙️  Backend Errors",
            "frontend": "🎨 Frontend Errors",
            "node": "📦 Node.js / Package Manager Errors",
            "database": "🗄️  Database Errors",
            "infra": "🐳 Infrastructure / Container Errors",
            "crash": "💥 Crash Reports",
            "build": "🔨 Build / Compilation Errors",
            "security": "🔒 Security / Auth Errors",
        }
        label = category_labels.get(cat_name, f"📁 {cat_name.capitalize()} Errors")
        print(f" ── {label} ({cat_data['total']}) ──")

        for pat_name, pat_data in sorted(cat_data.get("patterns", {}).items()):
            print(f"\n   🔍 {pat_name} ({pat_data['count']} occurrences)")

            # Last error
            le = pat_data["last_error"]
            print(f"      Last error  : line {le['line']} in {Path(le['file']).name}")
            le_msg = le["message"][:120]
            print(f"      Message     : {le_msg}")

            # Most frequent
            mf = pat_data["most_frequent"]
            mf_msg = mf["message"][:120]
            print(f"      Most frequent: \"{mf_msg}\" ({mf['occurrences']}x)")

            # Affected files
            files = pat_data["affected_files"]
            if len(files) <= 3:
                for f in files:
                    print(f"      📄 {f}")
            else:
                print(f"      📄 Affects {len(files)} files (shown: first 3)")
                for f in files[:3]:
                    print(f"         {f}")

            # Cause and fix
            print(f"      💡 Possible cause : {pat_data['possible_cause']}")
            print(f"      🔧 Recommended fix: {pat_data['recommended_fix']}")

        print()

    print(f"{'='*60}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="log_viewer.py — Scan and summarize errors in project log files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python log_viewer.py .                          # Scan current directory
  python log_viewer.py /path/to/project           # Scan specific path
  python log_viewer.py . --json                   # JSON output
  python log_viewer.py . --since "2025-01-01"     # Filter by date
  python log_viewer.py . --type error,warn        # Filter by category
        """,
    )
    parser.add_argument("path", nargs="?", default=".",
                        help="Project root directory to scan for log files")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--since", type=str, default=None,
                        help="Only show errors after this date (YYYY-MM-DD)")
    parser.add_argument("--type", type=str, default=None,
                        help="Comma-separated list of error categories to show "
                             "(python,backend,frontend,node,database,infra,crash,build,security)")
    parser.add_argument("--version", action="version",
                        version="log_viewer.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 Log Viewer v1.0.0 — scanning {target}")

    # Discover log files
    log_files = discover_log_files(target)

    if not log_files:
        print(" ℹ️  No log files found.")
        if args.json:
            print(json.dumps({
                "target": str(target),
                "log_files_found": 0,
                "total_errors": 0,
                "categories": {},
                "summary": "No log files found.",
            }, indent=2, ensure_ascii=False))
        sys.exit(0)

    print(f" 📁 Found {len(log_files)} log file(s)")

    # Scan each file for errors
    all_errors: list[dict] = []
    scanned_count = 0
    for lf in log_files:
        errors = scan_file_for_errors(lf)
        if errors:
            all_errors.extend(errors)
            scanned_count += 1

    print(f" 🔍 Scanned {scanned_count} file(s) with errors found")

    # Filter by type if requested
    if args.type:
        allowed_types = set(t.strip().lower() for t in args.type.split(","))
        all_errors = [e for e in all_errors if e["category"] in allowed_types]

    # Filter by date if requested
    if args.since:
        try:
            since_dt = datetime.strptime(args.since, "%Y-%m-%d")
            # For date filtering, we'd need to extract timestamps from each error's context
            # This is best-effort: filter errors in files whose
            # names/mtime suggest recent activity
            filtered = []
            for err in all_errors:
                fp = Path(err["file"])
                try:
                    mtime = datetime.fromtimestamp(fp.stat().st_mtime)
                    if mtime >= since_dt:
                        filtered.append(err)
                except Exception:
                    filtered.append(err)  # Keep if we can't check
            all_errors = filtered
        except ValueError:
            print(f" ⚠ Invalid date format for --since: '{args.since}'. Use YYYY-MM-DD.", file=sys.stderr)
            sys.exit(2)

    # Categorize and summarize
    stats = categorize_and_summarize(all_errors)

    if args.json:
        output = {
            "target": str(target),
            "log_files_found": len(log_files),
            "files_with_errors": scanned_count,
            **stats,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print_report(stats, target)

    # Exit codes: 0 = no errors, 1 = errors found, 2 = usage error
    if stats["total_errors"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()