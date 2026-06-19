#!/usr/bin/env python3
"""
changelog_generator.py — Generate changelogs from git history, patches, or reports.

Sources:
  - git log (conventional commit format)
  - git diff (parsed for additions/removals)
  - patches folder (directory with .patch / .diff / .txt files)
  - stdin (piped content)

Output sections:
  ## Added
  ## Fixed
  ## Changed
  ## Security
  ## Removed

Exit codes:
  0 — success
  1 — runtime error (git not found, path not found, etc.)
  2 — usage error (bad flags, missing arguments)

Usage:
    python changelog_generator.py --git-log <range>
    python changelog_generator.py --git-diff <range>
    python changelog_generator.py --patches <folder>
    python changelog_generator.py --stdin
    python changelog_generator.py --git-log HEAD~5..HEAD --json
"""

from __future__ import annotations

__maker__ = "SmokerGreenOG"

import _protect

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

# ---------------------------------------------------------------------------
# Section keys — order matters for output
# ---------------------------------------------------------------------------
SECTIONS = ["Added", "Fixed", "Changed", "Security", "Removed"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_title(line: str) -> str:
    """Strip common prefixes like 'feat:', 'fix:', trailing punctuation."""
    line = re.sub(r'^[\w-]+(\s*\([\w.-]+\))?\s*:\s*', '', line, flags=re.IGNORECASE)
    return line.strip().rstrip(".,;:!?")


def _categorise_conventional(commit_type: str) -> str:
    """Map a conventional-commit type to a changelog section."""
    mapping = {
        "feat": "Added",
        "feature": "Added",
        "add": "Added",
        "implement": "Added",
        "introduce": "Added",

        "fix": "Fixed",
        "bugfix": "Fixed",
        "bug": "Fixed",
        "hotfix": "Fixed",
        "patch": "Fixed",
        "resolve": "Fixed",
        "repair": "Fixed",

        "refactor": "Changed",
        "refact": "Changed",
        "update": "Changed",
        "improve": "Changed",
        "improvement": "Changed",
        "change": "Changed",
        "modify": "Changed",
        "migrate": "Changed",
        "migration": "Changed",
        "perf": "Changed",
        "performance": "Changed",
        "optimise": "Changed",
        "optimize": "Changed",
        "style": "Changed",
        "chore": "Changed",
        "ci": "Changed",
        "build": "Changed",
        "deps": "Changed",
        "dependencies": "Changed",
        "config": "Changed",
        "configuration": "Changed",

        "security": "Security",
        "sec": "Security",

        "remove": "Removed",
        "deprecate": "Removed",
        "deprecation": "Removed",
        "drop": "Removed",
        "delete": "Removed",
        "cleanup": "Removed",
        "clean": "Removed",
        "revert": "Removed",
    }
    return mapping.get(commit_type.lower() if commit_type else "", "")


def _categorise_line(line: str) -> str:
    """
    Heuristic categorisation for lines that aren't from conventional commits.
    Tries to infer section from leading keywords.
    """
    lower = line.strip().lower()

    # Added
    if lower.startswith(("add", "new", "implement", "introduce", "support for",
                          "added", "feature")):
        return "Added"

    # Fixed
    if lower.startswith(("fix", "bug", "patch", "hotfix", "resolve", "repair",
                          "correct", "fixes", "fixed")):
        return "Fixed"

    # Removed
    if lower.startswith(("remov", "deprecat", "drop", "delete", "cleanup",
                          "revert", "removed")):
        return "Removed"

    # Security
    if lower.startswith(("security", "cve", "vulnerability", "xss", "csrf",
                          "injection", "auth bypass", "privilege", "secure")):
        return "Security"

    # Changed (default for everything else)
    return "Changed"


# ---------------------------------------------------------------------------
# Changelog data structure
# ---------------------------------------------------------------------------

class Changelog:
    """Holds items per section and renders to text or JSON."""

    def __init__(self) -> None:
        self._data: Dict[str, List[str]] = {s: [] for s in SECTIONS}

    def add_item(self, section: str, description: str) -> None:
        """Add an item to *section* (resolved automatically on empty)."""
        if not section:
            section = self._resolve_section(description)
        # Ensure section is valid
        if section not in self._data:
            section = "Changed"
        self._data[section].append(description.strip().rstrip(".,;:!?"))

    @staticmethod
    def _resolve_section(description: str) -> str:
        return _categorise_line(description)

    def merge(self, other: "Changelog") -> None:
        """Merge another Changelog into this one."""
        for sec in SECTIONS:
            self._data[sec].extend(other._data[sec])

    @property
    def is_empty(self) -> bool:
        return all(len(v) == 0 for v in self._data.values())

    def total_items(self) -> int:
        return sum(len(v) for v in self._data.values())

    def render_text(self) -> str:
        """Render as Markdown changelog."""
        lines: List[str] = []
        for sec in SECTIONS:
            items = self._data[sec]
            if not items:
                continue
            lines.append(f"## {sec}")
            for item in items:
                # Indent multi-line descriptions
                for i, line in enumerate(item.split("\n")):
                    prefix = "  " if i > 0 else "- "
                    lines.append(f"{prefix}{line}")
            lines.append("")  # blank line after section
        return "\n".join(lines)

    def render_json(self) -> str:
        """Render as JSON object."""
        return json.dumps(self._data, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Source parsers
# ---------------------------------------------------------------------------

def parse_git_log(revision_range: str = "HEAD", cwd: Optional[Path] = None) -> Changelog:
    """Parse ``git log`` output using conventional-commit format."""
    cl = Changelog()
    try:
        cmd = [
            "git", "log",
            f"--pretty=format:%s|||%b",
            revision_range,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd else None,
        )
    except FileNotFoundError:
        print("Error: git not found on PATH", file=sys.stderr)
        sys.exit(EXIT_ERROR)

    if result.returncode != 0:
        err = result.stderr.strip()
        print(f"Error: git log failed — {err}", file=sys.stderr)
        sys.exit(EXIT_ERROR)

    raw = result.stdout.strip()
    if not raw:
        return cl

    entries = raw.split("\n\n")
    for entry in entries:
        if not entry.strip():
            continue
        parts = entry.split("|||", 1)
        subject = parts[0].strip()
        body = parts[1].strip() if len(parts) > 1 else ""

        # Try to extract conventional-commit type
        type_match = re.match(r'^(\w+)(?:\([\w.-]+\))?\s*:\s*(.*)', subject, re.IGNORECASE)
        if type_match:
            commit_type = type_match.group(1)
            title = type_match.group(2).strip()
            section = _categorise_conventional(commit_type)
        else:
            title = _clean_title(subject)
            section = _categorise_line(title)

        cl.add_item(section, title)

        # Also parse body lines that look meaningful (conventional body bullets)
        if body:
            for bline in body.split("\n"):
                bline = bline.strip()
                if not bline:
                    continue
                # Skip common boilerplate
                if bline.lower().startswith(("signed-off-by", "co-authored-by",
                                              "reviewed-by", "acked-by", "change-id",
                                              "refs:", "see also:")):
                    continue
                # Treat as a changelog bullet if it looks descriptive
                if len(bline) > 15:
                    sub_section = _categorise_line(bline)
                    cl.add_item(sub_section, bline)

    return cl


def parse_git_diff(revision_range: str = "HEAD", cwd: Optional[Path] = None) -> Changelog:
    """Parse ``git diff`` output — infer changes from file-level diffs."""
    cl = Changelog()
    try:
        cmd = [
            "git", "diff",
            "--stat",
            revision_range,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd else None,
        )
    except FileNotFoundError:
        print("Error: git not found on PATH", file=sys.stderr)
        sys.exit(EXIT_ERROR)

    if result.returncode != 0:
        err = result.stderr.strip()
        print(f"Error: git diff failed — {err}", file=sys.stderr)
        sys.exit(EXIT_ERROR)

    raw = result.stdout.strip()
    if not raw:
        return cl

    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Skip totals line
        if line.startswith((" ", "files changed", "file changed")):
            continue
        if " | " in line:
            file_path = line.split(" | ")[0].strip()
            if not file_path:
                continue
            # Categorise by path keywords
            lower_path = file_path.lower()
            if any(kw in lower_path for kw in ("test", "spec", "__test__")):
                cl.add_item("Changed", f"Updated tests: {file_path}")
            elif any(kw in lower_path for kw in ("security", "auth", "cve", "vuln")):
                cl.add_item("Security", f"Updated security-related file: {file_path}")
            elif any(kw in lower_path for kw in ("deprecat", "remov", "delete", "cleanup")):
                cl.add_item("Removed", f"Cleaned up: {file_path}")
            elif any(kw in lower_path for kw in ("new", "add", "create", "init")):
                cl.add_item("Added", f"Added: {file_path}")
            else:
                cl.add_item("Changed", f"Modified: {file_path}")

    return cl


def parse_patches_dir(patch_dir: Path) -> Changelog:
    """Read .patch / .diff / .txt files from *patch_dir* and parse them."""
    cl = Changelog()

    if not patch_dir.is_dir():
        print(f"Error: patches folder not found — {patch_dir}", file=sys.stderr)
        sys.exit(EXIT_ERROR)

    patch_files = sorted(
        p for p in patch_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".patch", ".diff", ".txt"}
    )

    if not patch_files:
        print(f"Warning: no .patch / .diff / .txt files in {patch_dir}", file=sys.stderr)
        return cl

    for pf in patch_files:
        try:
            text = pf.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            print(f"Warning: could not read {pf.name} — {exc}", file=sys.stderr)
            continue

        # Try to extract from Subject: header first
        title = ""
        body_start = False
        for tline in text.split("\n"):
            tline_stripped = tline.strip()
            subj_match = re.match(r"^Subject:\s*(.+)$", tline_stripped, re.IGNORECASE)
            if subj_match:
                title = subj_match.group(1).strip()
                continue
            # Detect end of headers (blank line before body)
            if not body_start and not tline_stripped and title:
                body_start = True
                continue

        # If no Subject, find first non-metadata line
        if not title:
            for tline in text.split("\n"):
                tline = tline.strip()
                if not tline:
                    continue
                if tline.startswith(("---", "+++", "@@", "diff --git",
                                      "index ", "new file", "deleted file",
                                      "From ", "From:", "Date: ", "Subject: ")):
                    continue
                title = tline.rstrip(".,;:!?")
                break

        filename = pf.stem
        if title:
            # Also try to categorise based on title prefix
            sec = _categorise_line(title)
            # Check for conventional prefixes in the Subject line
            subj_prefix = re.match(r'^(\w+)\s*:\s*(.*)', title)
            if subj_prefix:
                mapped = _categorise_conventional(subj_prefix.group(1))
                if mapped:
                    sec = mapped
                    title = subj_prefix.group(2).strip()
            cl.add_item(sec, f"{title} ({filename})")
        else:
            cl.add_item("Changed", f"Patch: {filename}")

    return cl


def parse_stdin() -> Changelog:
    """Read changelog-style lines from stdin."""
    cl = Changelog()

    lines = sys.stdin.read().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip markdown headers
        if line.startswith("#"):
            continue
        # Strip leading bullet markers
        raw = re.sub(r'^[\s*•\-–—+>]+\s*', '', line)
        if raw:
            cl.add_item("", raw)

    return cl


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Build and parse argument parser."""
    parser = argparse.ArgumentParser(
        description="Generate changelogs from git history, patches, or stdin.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --git-log HEAD~10..HEAD\n"
            "  %(prog)s --git-diff main..feature-branch\n"
            "  %(prog)s --patches ./patches\n"
            "  cat report.txt | %(prog)s --stdin\n"
            "  %(prog)s --git-log HEAD~5..HEAD --json\n"
        ),
    )

    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--git-log",
        metavar="RANGE",
        nargs="?",
        const="HEAD",
        default=None,
        help="Read commits via `git log` (default range: HEAD)",
    )
    source.add_argument(
        "--git-diff",
        metavar="RANGE",
        nargs="?",
        const="HEAD",
        default=None,
        help="Read file changes via `git diff --stat` (default range: HEAD)",
    )
    source.add_argument(
        "--patches",
        metavar="DIR",
        type=Path,
        default=None,
        help="Directory containing .patch / .diff / .txt files",
    )
    source.add_argument(
        "--stdin",
        action="store_true",
        default=False,
        help="Read changelog lines from stdin",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output as JSON instead of Markdown",
    )

    parser.add_argument(
        "--cwd",
        type=Path,
        default=None,
        help="Working directory for git commands (default: current dir)",
    )

    parsed = parser.parse_args(argv)

    # Validate that at least one source was specified
    if not any([parsed.git_log, parsed.git_diff, parsed.patches, parsed.stdin]):
        parser.error(
            "No source specified. Use one of: --git-log, --git-diff, "
            "--patches, or --stdin"
        )

    return parsed


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point. Returns exit code."""
    try:
        args = parse_args(argv)
    except SystemExit:
        # argparse sys.exit(2) — usage error
        return EXIT_USAGE

    try:
        # Dispatch to the appropriate parser
        if args.git_log:
            cl = parse_git_log(args.git_log, cwd=args.cwd)
        elif args.git_diff:
            cl = parse_git_diff(args.git_diff, cwd=args.cwd)
        elif args.patches:
            cl = parse_patches_dir(args.patches)
        elif args.stdin:
            cl = parse_stdin()
        else:
            # Should not happen due to mutually exclusive group + validation
            print("Error: no source specified", file=sys.stderr)
            return EXIT_USAGE

        if cl.is_empty:
            print("No changelog entries found.", file=sys.stderr)
            return EXIT_SUCCESS

        # Render and print
        if args.json:
            print(cl.render_json())
        else:
            print(cl.render_text())

        return EXIT_SUCCESS

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_ERROR

    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
