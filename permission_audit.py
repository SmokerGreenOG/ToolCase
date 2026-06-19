#!/usr/bin/env python3
"""
permission_audit.py — Agent Permission Auditor

Simulates checking what permissions the Hermes agent has.
No actual system modifications are performed.

Usage:
    python permission_audit.py              # Human-readable table
    python permission_audit.py --json       # JSON output
    python permission_audit.py --help       # This help
"""

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import datetime
import json
import sys
import os
from typing import Optional


# ── Permission definitions ────────────────────────────────────────────────────
PERMISSIONS = [
    {
        "name": "can_read",
        "label": "Read files",
        "description": "Ability to read files from the filesystem.",
        "default": "Allowed",
        "reason": "Agent can read any file within workspace and system paths.",
    },
    {
        "name": "can_write",
        "label": "Write files",
        "description": "Ability to write and modify files on disk.",
        "default": "Allowed",
        "reason": "Agent can create and overwrite files within workspace.",
    },
    {
        "name": "can_use_terminal",
        "label": "Use terminal",
        "description": "Ability to execute shell commands.",
        "default": "Allowed",
        "reason": "Agent has full shell execution access via terminal tool.",
    },
    {
        "name": "can_install_deps",
        "label": "Install dependencies",
        "description": "Ability to install Python packages and system tools.",
        "default": "Requires Approval",
        "reason": (
            "Package installation modifies the runtime environment and may "
            "introduce untrusted code or break existing dependencies."
        ),
    },
    {
        "name": "can_read_env",
        "label": "Read .env files",
        "description": "Ability to read environment / secrets files (.env, credentials).",
        "default": "Requires Approval",
        "reason": (
            ".env files often contain API keys, tokens, and secrets. "
            "Reading them should be gated behind explicit user consent."
        ),
    },
    {
        "name": "can_use_internet",
        "label": "Use internet",
        "description": "Ability to make network requests (HTTP, API calls).",
        "default": "Requires Approval",
        "reason": (
            "Outbound network access can exfiltrate data or interact with "
            "external services. Approval ensures the user is aware."
        ),
    },
    {
        "name": "can_write_outside_workspace",
        "label": "Write outside workspace",
        "description": "Ability to write files outside the designated workspace directory.",
        "default": "Dangerous",
        "reason": (
            "Writing outside the workspace can modify system files, user "
            "documents, or other critical locations without the user's awareness."
        ),
    },
    {
        "name": "can_delete_files",
        "label": "Delete files",
        "description": "Ability to delete or remove files from disk.",
        "default": "Dangerous",
        "reason": (
            "File deletion is irreversible in many contexts and can cause "
            "data loss. This permission should be carefully controlled."
        ),
    },
]


# ── Output helpers ────────────────────────────────────────────────────────────

_STATUS_COLORS = {
    "Allowed": "\033[92m",       # green
    "Requires Approval": "\033[93m",  # yellow
    "Dangerous": "\033[91m",     # red
    "Blocked": "\033[90m",       # grey
}
_RESET = "\033[0m"


def _colorize(status: str) -> str:
    color = _STATUS_COLORS.get(status, "")
    if color and sys.stdout.isatty():
        return f"{color}{status}{_RESET}"
    return status


def _icon(status: str) -> str:
    icons = {
        "Allowed": "✓",
        "Requires Approval": "⚠",
        "Dangerous": "✗",
        "Blocked": "⊘",
    }
    return icons.get(status, "?")


def build_report(permissions: list[dict], include_reason: bool = False) -> list[dict]:
    """Build a list of dicts (one per permission)."""
    report = []
    for p in permissions:
        entry = {
            "permission": p["name"],
            "label": p["label"],
            "status": p["default"],
            "description": p["description"],
        }
        if include_reason:
            entry["reason"] = p["reason"]
        report.append(entry)
    return report


def print_table(report: list[dict]) -> None:
    """Print a human-readable table."""
    # Column widths
    label_w = max(len(e["label"]) for e in report) + 2
    status_w = max(len(e["status"]) for e in report) + 2

    header = (f"  {'Permission':<{label_w}}  {'Status':<{status_w}}  "
              f"Description")
    sep = "  " + "-" * (label_w + status_w + 50)

    print("Permission Audit Report")
    print("=" * 70)
    print()
    print(header)
    print(sep)

    for entry in report:
        label = entry["label"]
        status = _colorize(entry["status"])
        icon = _icon(entry["status"])
        desc = entry["description"]
        line = (f"  {icon} {label:<{label_w - 2}}  {status:<{status_w}}  "
                f"{desc}")
        print(line)

    print()
    # Summary counts
    counts = {}
    for e in report:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    parts = [f"{_colorize(k)}: {v}" for k, v in sorted(counts.items())]
    print("  Summary — " + "  |  ".join(parts))

    print()
    print("  ═  All checks are simulated — no actual system permissions")
    print("       were queried or modified.")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agent Permission Auditor — simulate-check what the agent can do.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  %(prog)s                  # table output\n"
            "  %(prog)s --json           # JSON output with reasons\n"
            "  %(prog)s --help           # this message\n"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (includes reason field).",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    report = build_report(PERMISSIONS, include_reason=args.json)

    if args.json:
        output = {
            "tool": "permission_audit",
            "description": "Simulated permission audit — no actual modifications",
            "workspace": os.path.abspath(os.getcwd()),
            "timestamp": datetime.datetime.now().isoformat(),
            "permissions": report,
        }
        json.dump(output, sys.stdout, indent=2)
        print()
    else:
        print_table(report)

    sys.exit(0)


if __name__ == "__main__":
    main()
