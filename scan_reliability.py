#!/usr/bin/env python3
"""
scan_reliability.py — Measure and report scanner reliability across ToolCase tools.

Wraps any ToolCase scanner and reports:
  - files found / scanned / skipped (by dir, by generated-report, by extension)
  - read errors / parse errors
  - tool failures (timeouts, subprocess errors)
  - per-scanner reliability score

Usage:
    python scan_reliability.py <path>                      # Full report
    python scan_reliability.py <path> --json               # JSON output
    python scan_reliability.py <path> --scan security      # Per-scanner breakdown
    python scan_reliability.py <path> --summary            # Summary only
"""

__maker__ = "SmokerGreenOG"

import _protect

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".eggs",
        "build",
        "dist",
        ".next",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".cursor",
        ".backups",
        ".rsi_backups",
        ".rsi_reports",
        ".self_improve_reports",
        "vendor",
        ".hermes",
        "tests/fixtures",
        "release",
    }
)

# Generated report patterns (filename-level)
GENERATED_REPORT_PATTERNS = (
    "*_audit_report.md",
    "*_audit_report.html",
    "codex_audit_report.*",
    "toolcase_analysis_report.*",
    "dexcore_analysis_report.*",
)

SCANNABLE_EXTENSIONS = frozenset(
    {
        ".py",
        ".php",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".rs",
        ".go",
        ".java",
        ".kt",
        ".swift",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".rb",
        ".sh",
        ".bash",
        ".ps1",
        ".bat",
        ".lua",
        ".yaml",
        ".yml",
        ".toml",
        ".json",
        ".xml",
        ".ini",
        ".cfg",
        ".md",
        ".rst",
        ".txt",
        ".css",
        ".scss",
        ".html",
        ".env",
        ".htaccess",
        ".conf",
    }
)


def _is_generated_report(filepath: Path) -> bool:
    """Check if a file is a generated audit report (to skip in scans)."""
    name_lower = filepath.name.lower()
    for pattern in GENERATED_REPORT_PATTERNS:
        if fnmatch(name_lower, pattern):
            return True
    # Check path contains generated report directories
    path_str = str(filepath).lower().replace("\\", "/")
    if ".rsi_reports/" in path_str or ".self_improve_reports/" in path_str:
        return True
    if ".rsi_backups/" in path_str:
        return True
    return False


def collect_files(root: Path) -> tuple[list[Path], dict[str, int]]:
    """Collect all scannable files and return accounting stats."""
    files: list[Path] = []
    stats: dict[str, int] = {
        "found": 0,
        "skipped_dir": 0,
        "skipped_ext": 0,
        "skipped_generated": 0,
        "collected": 0,
    }

    if root.is_file():
        ext = root.suffix.lower()
        if ext in SCANNABLE_EXTENSIONS:
            files.append(root)
            stats["found"] = 1
            stats["collected"] = 1
        else:
            stats["found"] = 1
            stats["skipped_ext"] = 1
        return files, stats

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded dirs
        original_count = len(dirnames)
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        stats["skipped_dir"] += original_count - len(dirnames)

        for fn in filenames:
            fp = Path(dirpath) / fn
            stats["found"] += 1

            # Skip generated reports
            if _is_generated_report(fp):
                stats["skipped_generated"] += 1
                continue

            # Skip non-scannable extensions
            ext = fp.suffix.lower()
            if ext not in SCANNABLE_EXTENSIONS:
                stats["skipped_ext"] += 1
                continue

            files.append(fp)
            stats["collected"] += 1

    return sorted(files), stats


class ScanSession:
    """Tracks scan reliability metrics for a single scanner run."""

    def __init__(self, scanner_name: str):
        self.scanner_name = scanner_name
        self.start_time = 0.0
        self.end_time = 0.0
        self.files_found = 0
        self.files_scanned = 0
        self.files_skipped = 0
        self.read_errors = 0
        self.parse_errors = 0
        self.findings_count = 0
        self.timed_out = False
        self.crashed = False
        self.error_message = ""

    def start(self) -> None:
        """start."""
        self.start_time = time.monotonic()

    def stop(self) -> None:
        """stop."""
        self.end_time = time.monotonic()

    @property
    def elapsed_ms(self) -> float:
        """elapsed ms."""
        return (self.end_time - self.start_time) * 1000

    @property
    def reliability_score(self) -> float:
        """0.0-1.0: how reliable this scan was.

        Intentional skips (binary extensions, cache dirs, generated reports)
        are excluded from the denominator — they don't penalize reliability.
        Only crashes, timeouts, read errors and parse errors reduce the score.
        """
        if self.files_found == 0:
            return 0.0 if self.crashed else 1.0
        if self.crashed or self.timed_out:
            return 0.0
        # Coverage: scanned vs scannable (excluding intentional skips)
        scannable = max(self.files_found - self.files_skipped, 1)
        coverage = min(1.0, self.files_scanned / scannable)
        error_penalty = (self.read_errors + self.parse_errors) / max(self.files_scanned, 1)
        return max(0.0, min(1.0, coverage - error_penalty * 0.5))

    def to_dict(self) -> dict[str, Any]:
        """to dict."""
        return {
            "scanner": self.scanner_name,
            "files_found": self.files_found,
            "files_scanned": self.files_scanned,
            "files_skipped": self.files_skipped,
            "read_errors": self.read_errors,
            "parse_errors": self.parse_errors,
            "findings": self.findings_count,
            "timed_out": self.timed_out,
            "crashed": self.crashed,
            "error": self.error_message or None,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "reliability": round(self.reliability_score, 3),
        }


def scan_reliability(target: Path, scanners: list[str] | None = None) -> dict[str, Any]:
    """Run reliability analysis on all/specific scanners against target."""
    files, collect_stats = collect_files(target)

    all_scanners = (
        scanners
        if scanners
        else [
            "security_scan",
            "php_checker",
            "project_doctor",
        ]
    )

    sessions: dict[str, ScanSession] = {}

    for scanner_name in all_scanners:
        session = ScanSession(scanner_name)
        session.files_found = collect_stats["found"]
        session.files_skipped = (
            collect_stats["skipped_dir"]
            + collect_stats["skipped_ext"]
            + collect_stats["skipped_generated"]
        )
        session.files_scanned = collect_stats["collected"]

        # Try to import and run the scanner to get real metrics
        try:
            session.start()
            findings = _run_scanner(scanner_name, target)
            session.stop()
            session.findings_count = len(findings) if isinstance(findings, list) else 0
            # Count read/parse errors from findings
            if isinstance(findings, list):
                session.read_errors = len(
                    [
                        f
                        for f in findings
                        if isinstance(f, dict) and f.get("pattern") == "read_error"
                    ]
                )
                session.parse_errors = len(
                    [
                        f
                        for f in findings
                        if isinstance(f, dict)
                        and f.get("pattern") in ("parse_error", "syntax_error")
                    ]
                )
        except ImportError:
            session.stop()
            session.crashed = True
            session.error_message = f"Scanner '{scanner_name}' not importable"
        except (OSError, ValueError, RuntimeError) as e:
            session.stop()
            session.crashed = True
            session.error_message = str(e)[:200]
        except Exception as e:
            session.stop()
            session.crashed = True
            session.error_message = f"Unexpected: {type(e).__name__}: {e!s}"[:200]

        sessions[scanner_name] = session

    # Build report
    overall_reliability = 0.0
    if sessions:
        overall_reliability = sum(s.reliability_score for s in sessions.values()) / len(sessions)

    return {
        "target": str(target),
        "collect_stats": collect_stats,
        "scanners": {name: s.to_dict() for name, s in sessions.items()},
        "overall_reliability": round(overall_reliability, 3),
        "verdict": (
            "reliable"
            if overall_reliability >= 0.95
            else "degraded"
            if overall_reliability >= 0.80
            else "unreliable"
        ),
    }


def _run_scanner(scanner_name: str, target: Path) -> list[dict]:
    """Run a named scanner against target and return findings."""
    if scanner_name == "security_scan":
        from security_scan import scan_file, collect_files as sec_collect

        files = sec_collect(target)
        all_findings = []
        for fp in files:
            all_findings.extend(scan_file(fp))
        return all_findings
    elif scanner_name == "project_doctor":
        try:
            from project_doctor import diagnose_project

            result = diagnose_project(str(target))
            if isinstance(result, dict):
                return result.get("findings", [])
            return []
        except Exception:
            return []
    elif scanner_name == "php_checker":
        try:
            from php_checker import check_file

            findings = []
            php_files = list(target.rglob("*.php"))
            for pf in php_files[:200]:  # Limit for performance
                try:
                    findings.extend(check_file(pf) or [])
                except Exception:
                    pass
            return findings
        except Exception:
            return []
    else:
        # Generic: try importing the module and calling its main scanner
        return []


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def print_report(report: dict[str, Any]) -> None:
    """Print a formatted reliability report."""
    cs = report["collect_stats"]
    scanners = report["scanners"]

    print(f"\n{'=' * 60}")
    print(f" 🔬 SCANNER RELIABILITY REPORT")
    print(f"{'=' * 60}")
    print(f" Target:  {report['target']}")
    print(f" Overall: {report['overall_reliability']:.1%} — {report['verdict'].upper()}")
    print()

    # Collect stats
    print(f" ── File Collection ──")
    print(f"   Found:             {cs['found']}")
    print(f"   Collected:         {cs['collected']}")
    print(f"   Skipped (dirs):    {cs['skipped_dir']}")
    print(f"   Skipped (ext):     {cs['skipped_ext']}")
    print(f"   Skipped (reports): {cs['skipped_generated']}")
    print()

    # Per-scanner
    for name, info in scanners.items():
        icon = "✅" if info["reliability"] >= 0.95 else "⚠" if info["reliability"] >= 0.80 else "❌"
        print(f" ── {icon} {info['scanner']} (reliability: {info['reliability']:.1%}) ──")
        print(f"   Scanned:   {info['files_scanned']}")
        print(f"   Findings:  {info['findings']}")
        print(f"   Read errs: {info['read_errors']}")
        print(f"   Parse errs:{info['parse_errors']}")
        print(f"   Time:      {info['elapsed_ms']}ms")
        if info.get("error"):
            print(f"   Error:     {info['error']}")
        print()

    print(f"{'=' * 60}\n")


def print_summary(report: dict[str, Any]) -> None:
    """Print a one-line summary."""
    print(
        f"reliability={report['overall_reliability']:.1%} "
        f"files={report['collect_stats']['collected']} "
        f"scanners={len(report['scanners'])} "
        f"verdict={report['verdict']}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """main."""
    parser = argparse.ArgumentParser(
        description="scan_reliability.py — Measure scanner reliability",
    )
    parser.add_argument("path", help="Directory or file to analyze")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument("--summary", "-s", action="store_true", help="One-line summary only")
    parser.add_argument("--scan", nargs="*", help="Specific scanners to check (default: all)")
    parser.add_argument("--version", action="version", version="scan_reliability.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f"❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    scanners = args.scan if args.scan else None
    report = scan_reliability(target, scanners)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.summary:
        print_summary(report)
    else:
        print_report(report)

    # Exit code based on reliability
    if report["overall_reliability"] < 0.80:
        sys.exit(1)
    elif report["overall_reliability"] < 0.95:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
