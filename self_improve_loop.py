#!/usr/bin/env python3
"""
self_improve_loop.py — Autonomous self-improvement loop for ToolCase v3.0.

CLI commands:
    python self_improve_loop.py .                    # Default: dry-run, 1 cycle
    python self_improve_loop.py . --dry-run          # Analyse only, no changes
    python self_improve_loop.py . --cycles 3         # Max 3 improvement cycles
    python self_improve_loop.py . --apply            # Apply mode with backup+test+rollback
    python self_improve_loop.py . --json             # Machine-readable JSON output
    python self_improve_loop.py . --safe-only        # Only trailing whitespace, formatting, docs
    python self_improve_loop.py . --focus docs       # Focus on documentation
    python self_improve_loop.py . --focus security   # Focus on security
    python self_improve_loop.py . --focus code-quality  # Focus on code quality
    python self_improve_loop.py . --focus tests      # Focus on tests

Modes:
    dry-run    — Analyse only. No files modified. Improvement plan shown.
    safe-only  — Only trailing whitespace, formatting, docs, __init__.py, --help, --json fixes.
    apply      — Backup → preview → apply → test → rollback on failure.
    cycles     — Repeat self-improvement N times (max 5). Each cycle re-scans.

Exit codes:
    0  — No problems found / improvement succeeded
    1  — Warnings found
    2  — Errors found or tests failed
    3  — Rollback executed
    4  — Blocked by safety rule
"""

from __future__ import annotations

__maker__ = "SmokerGreenOG"

import _protect

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Constants ─────────────────────────────────────────────
TOOLCASE_DIR = Path(__file__).parent.resolve()
REPORT_DIR = TOOLCASE_DIR / ".self_improve_reports"
BACKUP_DIR = TOOLCASE_DIR / ".backups"
MAX_CYCLES_LIMIT = 5  # Hard limit to prevent infinite loops
TIMEOUT_SHORT = 30
TIMEOUT_MEDIUM = 60
TIMEOUT_LONG = 120

# ── Forbidden patterns (Rule 7) ─────────────────────────────
FORBIDDEN_COMMANDS = [
    "rm -rf", "rm -r /", "rm -rf /", "del /f /s",
    "git clean -fdx", "git clean -fd",
    "curl.*| sh", "curl.*| bash", "wget.*| sh", "wget.*| bash",
    "powershell.*DownloadFile", "powershell.*Invoke-WebRequest",
    "Invoke-Expression", "iex",
]

FORBIDDEN_FILE_READS = [
    ".env", ".env.local", ".env.production", ".env.example",
    "credentials", "secrets", "api_key", "token", "password",
    "id_rsa", "id_ed25519", ".netrc", ".npmrc._token",
]


# ── Data classes ────────────────────────────────────────────

@dataclass
class Finding:
    category: str  # code-quality | security | project-health | docs | tests | build
    severity: str  # critical | high | medium | low | info
    message: str
    file: str = ""
    line: int = 0
    suggestion: str = ""


@dataclass
class Change:
    description: str
    category: str  # safe | needs_approval | forbidden
    file: str = ""
    diff: str = ""
    backup_path: str = ""
    status: str = "planned"  # planned | applied | skipped | rolled_back
    reason: str = ""


@dataclass
class CycleReport:
    cycle: int
    mode: str  # dry-run | safe-only | apply
    focus: str  # all | docs | security | code-quality | tests
    findings: list[Finding] = field(default_factory=list)
    planned_improvements: list[Change] = field(default_factory=list)
    applied_changes: list[Change] = field(default_factory=list)
    skipped_changes: list[Change] = field(default_factory=list)
    backup_paths: list[str] = field(default_factory=list)
    tests: dict = field(
        default_factory=lambda: {
            "status": "not_run", "command": None, "details": []
        }
    )
    rollback: dict = field(default_factory=lambda: {"executed": False, "reason": None})
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = "passed"  # passed | warning | failed | rolled_back | blocked

    def final_exit_code(self) -> int:
        if self.status == "blocked":
            return 4
        if self.status == "rolled_back":
            return 3
        if self.status == "failed":
            return 2
        if self.status == "warning" or self.warnings:
            return 1
        return 0


# ── Safety Manager ──────────────────────────────────────────

class SafetyManager:
    """Enforces all 10 safety rules plus forbidden operations lists."""

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.backups: dict[str, Path] = {}

    # ── Rule 4: Workspace sandbox ──────────────────────────
    def within_workspace(self, path: str | Path) -> Path:
        p = Path(path).resolve()
        try:
            p.relative_to(self.workspace)
            return p
        except ValueError:
            raise PermissionError(
                f"SAFETY BLOCKED: {p} is outside workspace {self.workspace}"
            )

    # ── Rule 1: Backup ────────────────────────────────────
    def create_backup(self, path: str | Path) -> str | None:
        p = self.within_workspace(path)
        if not p.exists():
            return None
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = BACKUP_DIR / f"{p.name}.{ts}.bak"
        shutil.copy2(str(p), str(backup))
        self.backups[str(p)] = backup
        return str(backup)

    # ── Rule 7: No destructive commands ───────────────────
    def is_command_forbidden(self, cmd: str) -> str | None:
        cmd_lower = cmd.lower()
        for pattern in FORBIDDEN_COMMANDS:
            if pattern.lower() in cmd_lower:
                return f"Command matches forbidden pattern: {pattern}"
        return None

    # ── Rule 2: No secrets printed ────────────────────────
    def is_file_forbidden_to_read(self, path: str | Path) -> str | None:
        name = Path(path).name.lower()
        for pattern in FORBIDDEN_FILE_READS:
            if pattern in name:
                return f"File contains sensitive pattern: {pattern}"
        return None

    # ── Rule 5: Approval prompt ───────────────────────────
    def require_approval(self, action: str, details: str) -> bool:
        print(f"\n  ⚠  Approval needed: {action}")
        print(f"     {details}")
        print(f"  [y/N] ", end="", flush=True)
        try:
            return input().strip().lower() in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    # ── Rule 10: Rollback ─────────────────────────────────
    def rollback(self, path: str | Path) -> bool:
        p = str(path)
        if p in self.backups:
            backup = self.backups[p]
            if backup.exists():
                shutil.copy2(str(backup), p)
                return True
        return False


# ── Scanners ─────────────────────────────────────────────────

class CodeScanner:
    """Runs ToolCase tools and collects findings."""

    def __init__(self, workspace: Path, focus: str = "all"):
        self.workspace = workspace
        self.focus = focus

    def _run_tool(self, script: str, args: list[str],
                  timeout: int = TIMEOUT_MEDIUM) -> dict:
        tool = TOOLCASE_DIR / script
        if not tool.exists():
            return {"error": f"Tool not found: {script}"}
        try:
            r = subprocess.run(
                [sys.executable, str(tool)] + args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            output = (r.stdout + r.stderr).strip()
            return {"exit_code": r.returncode, "output": output}
        except subprocess.TimeoutExpired:
            return {"error": f"TIMEOUT ({timeout}s): {script}"}
        except Exception as e:
            return {"error": str(e)}

    def scan_files(self) -> list[Finding]:
        """Step 1: List all .py files in workspace."""
        files = sorted(self.workspace.rglob("*.py"))
        files = [f for f in files if not any(
            p.startswith(".") for p in f.relative_to(self.workspace).parts
        )]
        return [
            Finding(category="code-quality", severity="info",
                    message=f"Found {len(files)} .py files",
                    suggestion=""),
        ]

    def scan_code_quality(self) -> list[Finding]:
        """Step 2: Code quality via improve.py."""
        findings = []
        if self.focus not in ("all", "code-quality"):
            return findings

        r = self._run_tool("improve.py", [str(self.workspace), "--recursive"],
                           timeout=TIMEOUT_LONG)
        if r.get("error"):
            findings.append(Finding(
                category="code-quality", severity="warning",
                message=f"improve.py scan: {r['error']}",
            ))
            return findings

        output = r.get("output", "")
        for line in output.split("\n"):
            # Parse "    file.py:LINE | E501: Line too long..."
            stripped = line.strip()
            if not stripped:
                continue
            # Detect lint lines: "file.py:NN | E501|E302|W291|W293"
            lint_match = re.match(
                r'^(\S+?\.py):(\d+)\s*\|\s*(E\d+|W\d+)\s*:\s*(.+)$',
                stripped
            )
            if lint_match:
                fpath = lint_match.group(1)
                lnum = int(lint_match.group(2))
                code = lint_match.group(3)
                desc = lint_match.group(4).strip()[:90]
                # E501 (line too long) is info-only — can't auto-fix safely
                sev = "info"
                findings.append(Finding(
                    category="code-quality", severity=sev,
                    message=f"{fpath}:{lnum} | {code}: {desc}",
                    file=fpath, line=lnum,
                    suggestion=f"Consider wrapping line {lnum} in {fpath}",
                ))
                continue
            # Detect W291/W293 (trailing whitespace) — auto-fixable
            ws_match = re.match(
                r'^(\S+?\.py):(\d+)\s*\|\s*(W291|W293)\s*:\s*(.+)$',
                stripped
            )
            if ws_match:
                findings.append(Finding(
                    category="code-quality", severity="low",
                    message=stripped[:100],
                    file=ws_match.group(1),
                    line=int(ws_match.group(2)),
                    suggestion="Remove trailing whitespace",
                ))
        return findings

    def scan_security(self) -> list[Finding]:
        """Step 4: Security scan."""
        findings = []
        if self.focus not in ("all", "security"):
            return findings

        r = self._run_tool("security_scan.py", [str(self.workspace), "--json"])
        try:
            output = r.get("output", "")
            # Strip banner text before JSON
            json_start = output.find("{")
            if json_start >= 0:
                data = json.loads(output[json_start:])
                for f_item in data.get("findings", data.get("results", [])):
                    risk = f_item.get("risk", "MEDIUM").lower()
                    sev = {
                        "high": "critical",
                        "medium": "high",
                        "low": "medium",
                    }.get(risk, "medium")
                    findings.append(Finding(
                        category="security", severity=sev,
                        message=f_item.get("pattern", "Security issue"),
                        file=f_item.get("file", ""),
                        line=f_item.get("line", 0),
                        suggestion=f_item.get("fix", ""),
                    ))
            else:
                findings.append(Finding(
                    category="security", severity="warning",
                    message=f"Security scan output unparseable",
                ))
        except (json.JSONDecodeError, KeyError):
            findings.append(Finding(
                category="security", severity="warning",
                message="Could not parse security scan output",
            ))
        return findings

    def scan_todos(self) -> list[Finding]:
        """Step 3: TODO/FIXME markers."""
        findings = []
        if self.focus not in ("all", "code-quality"):
            return findings

        r = self._run_tool("todo_tracker.py", [str(self.workspace)])
        output = r.get("output", "")
        marker_count = 0
        for line in output.split("\n"):
            if "TODO" in line or "FIXME" in line or "HACK" in line:
                marker_count += 1
        if marker_count > 0:
            findings.append(Finding(
                category="code-quality", severity="medium",
                message=f"{marker_count} TODO/FIXME markers found",
                suggestion="Review and resolve stale markers",
            ))
        return findings

    def scan_dead_code(self) -> list[Finding]:
        """Step 3: Dead code."""
        findings = []
        if self.focus not in ("all", "code-quality"):
            return findings

        r = self._run_tool("dead_code_finder.py", [str(self.workspace)])
        output = r.get("output", "")
        for line in output.split("\n"):
            if "Ongebruikte" in line or "unused" in line.lower():
                findings.append(Finding(
                    category="code-quality", severity="medium",
                    message=line.strip()[:100],
                ))
        return findings

    def scan_project_health(self) -> list[Finding]:
        """Step 5: Project structure."""
        findings = []
        if self.focus not in ("all", "code-quality", "docs"):
            return findings

        # Check for __init__.py in subdirs
        for subdir in sorted(self.workspace.iterdir()):
            if subdir.is_dir() and not subdir.name.startswith("."):
                init = subdir / "__init__.py"
                if not init.exists():
                    findings.append(Finding(
                        category="project-health", severity="low",
                        message=f"Missing __init__.py in {subdir.name}/",
                        suggestion="Add empty __init__.py",
                    ))

        # Check for README
        if not (self.workspace / "README.md").exists():
            findings.append(Finding(
                category="docs", severity="high",
                message="Missing README.md",
                suggestion="Create README.md with project documentation",
            ))

        # Check for docs/ directory
        docs_dir = self.workspace / "docs"
        if not docs_dir.exists():
            findings.append(Finding(
                category="docs", severity="low",
                message="No docs/ directory",
                suggestion="Consider creating docs/ for documentation",
            ))

        return findings

    def scan_missing_help(self) -> list[Finding]:
        """Check tools for --help and --json."""
        findings = []
        if self.focus not in ("all", "code-quality"):
            return findings

        for pyfile in sorted(self.workspace.glob("*.py")):
            name = pyfile.name
            # Skip utility modules and private files
            if name.startswith("_") or name == "improve.py" or name in (
                "i18n.py", "_protect.py",
            ):
                continue
            content = pyfile.read_text(encoding="utf-8", errors="ignore")
            has_help = "--help" in content or "add_argument" in content
            has_json = "--json" in content or "json" in content.lower()
            if not has_help:
                findings.append(Finding(
                    category="code-quality", severity="medium",
                    message=f"{name} — missing --help / argparse",
                    file=name,
                    suggestion="Add argparse with --help support",
                ))
            if not has_json:
                findings.append(Finding(
                    category="code-quality", severity="low",
                    message=f"{name} — missing --json output",
                    file=name,
                    suggestion="Add --json flag for machine-readable output",
                ))
        return findings

    def scan_all(self) -> list[Finding]:
        """Run all scanners and return findings."""
        findings = []
        findings.extend(self.scan_files())
        findings.extend(self.scan_code_quality())
        findings.extend(self.scan_security())
        findings.extend(self.scan_todos())
        findings.extend(self.scan_dead_code())
        findings.extend(self.scan_project_health())
        findings.extend(self.scan_missing_help())
        return findings


# ── Improvement Planner ──────────────────────────────────────

class ImprovementPlanner:
    """Categorises findings into safe / needs_approval / forbidden changes."""

    SAFE_CATEGORIES = {
        "trailing_whitespace": "Remove trailing whitespace",
        "missing_init": "Add missing __init__.py",
        "docs_create": "Create docs/ directory",
    }

    APPROVAL_CATEGORIES = {
        "package_json": "Modify package.json",
        "requirements": "Modify requirements.txt",
        "install_deps": "Install dependencies",
        "config_files": "Modify config files",
        "logic_rewrite": "Rewrite tool logic",
        "delete_file": "Delete file",
        "rename_file": "Rename file",
        "terminal_cmd": "Run terminal command",
        "release_pkg": "Create release package",
    }

    FORBIDDEN_CATEGORIES = {
        "read_env": "Read .env file",
        "print_keys": "Print API keys",
        "outside_workspace": "Write outside workspace",
        "rm_rf": "Run rm -rf or destructive delete",
        "git_clean": "Run git clean -fdx",
        "curl_pipe_sh": "Download and execute code (curl | sh)",
        "powershell_download": "PowerShell download and execute",
        "secrets_to_log": "Write secrets to log",
    }

    REPORT_ONLY_CATEGORIES = {
        "line_too_long": "Line too long (E501) — needs manual review",
        "missing_help": "Missing --help — needs manual argparse",
        "missing_json": "Missing --json — needs manual implementation",
        "security_finding": "Security finding — review manually",
        "todo_marker": "TODO/FIXME marker — review manually",
        "dead_code_report": "Dead code report — review manually",
        "e302_format": "E302 blank lines — minor formatting",
    }

    def __init__(self, safety: SafetyManager, mode: str):
        self.safety = safety
        self.mode = mode  # dry-run | safe-only | apply

    def classify(self, finding: Finding) -> Change:
        """Classify a finding into a change with category."""
        msg_lower = finding.message.lower()

        # Check forbidden first
        if any(f in msg_lower for f in [".env", "api_key", "token", "secret", "password"]):
            cat = "forbidden"
            reason = "Contains sensitive data"
        elif "outside workspace" in msg_lower:
            cat = "forbidden"
            reason = "Outside workspace"
        elif "rm -rf" in msg_lower or "git clean" in msg_lower:
            cat = "forbidden"
            reason = "Destructive command"

        # Info-only findings (E501 line length, etc.) — report only
        elif finding.severity == "info":
            cat = "safe"
            reason = "Report-only — needs manual review"

        # Check needs approval
        elif any(a in msg_lower for a in ["package.json", "requirements.txt", "dependency",
                                           "config file", "rewrite", "delete", "rename",
                                           "terminal", "release"]):
            cat = "needs_approval"
            reason = "Requires explicit approval"
        elif finding.severity in ("critical", "high") and self.mode == "safe-only":
            cat = "needs_approval"
            reason = "Too risky for safe-only mode"

        # Trailing whitespace (W291/W293) — safe, auto-fixable
        elif "W291" in msg_lower or "W293" in msg_lower or "trailing" in msg_lower:
            cat = "safe"
            reason = "Auto-fixable: trailing whitespace"

        # Missing __init__.py or docs/ — safe, auto-fixable
        elif "__init__.py" in msg_lower:
            cat = "safe"
            reason = "Auto-fixable: create __init__.py"

        elif "docs/ directory" in msg_lower:
            cat = "safe"
            reason = "Auto-fixable: create docs/"

        # Everything else — report only (skip in apply mode)
        else:
            cat = "safe"
            reason = "Report-only — no auto-fix available"

        return Change(
            description=finding.message,
            category=cat,
            file=finding.file,
            reason=reason,
        )

    def plan(self, findings: list[Finding]) -> list[Change]:
        """Turn findings into a prioritised improvement plan."""
        changes = []
        for f in findings:
            c = self.classify(f)
            changes.append(c)

        # Sort: safe first, then needs_approval, then forbidden
        order = {"safe": 0, "needs_approval": 1, "forbidden": 2}
        changes.sort(key=lambda x: order.get(x.category, 99))

        return changes


# ── Executor ─────────────────────────────────────────────────

class Executor:
    """Applies safe changes with backup, preview, and validation."""

    def __init__(self, safety: SafetyManager, workspace: Path, mode: str):
        self.safety = safety
        self.workspace = workspace
        self.mode = mode
        self.applied: list[Change] = []
        self.skipped: list[Change] = []
        self.backup_paths: list[str] = []

    def _fix_trailing_whitespace(self, filepath: Path, change: Change) -> bool:
        """Actually remove trailing whitespace from a file."""
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
            new_content = "\n".join(line.rstrip() for line in content.split("\n"))
            if new_content != content:
                filepath.write_text(new_content, encoding="utf-8")
                change.description = f"Remove trailing whitespace: {filepath.name}"
                return True
            return False  # No change needed
        except Exception as e:
            change.reason = str(e)
            return False

    def _create_init_py(self, dirpath: Path, change: Change) -> bool:
        """Create an empty __init__.py."""
        try:
            init_file = dirpath / "__init__.py"
            if not init_file.exists():
                init_file.write_text(
                    f'# {dirpath.name} package\n'
                    f'# Auto-created by ToolCase self_improve_loop\n',
                    encoding="utf-8",
                )
                change.description = f"Create {dirpath.name}/__init__.py"
                return True
            return False
        except Exception as e:
            change.reason = str(e)
            return False

    def _create_docs_dir(self, change: Change) -> bool:
        """Create docs/ directory."""
        try:
            docs_dir = self.workspace / "docs"
            docs_dir.mkdir(exist_ok=True)
            if not (docs_dir / ".gitkeep").exists():
                (docs_dir / ".gitkeep").write_text("", encoding="utf-8")
            change.description = "Create docs/ directory"
            return True
        except Exception as e:
            change.reason = str(e)
            return False

    def apply(self, change: Change) -> str:
        """Apply a single change. Returns status: applied | skipped | rolled_back."""
        if self.mode == "dry-run":
            self.skipped.append(change)
            return "skipped (dry-run)"

        if change.category == "forbidden":
            change.status = "skipped"
            change.reason = "Forbidden by safety rules"
            self.skipped.append(change)
            return "skipped (forbidden)"

        if change.category == "needs_approval":
            if not self.safety.require_approval("Apply change",
                                                  change.description):
                change.status = "skipped"
                change.reason = "User declined approval"
                self.skipped.append(change)
                return "skipped (no approval)"
            change.category = "safe"

        if change.category == "safe":
            msg = change.description

            # ── Only fix these in safe-only mode ──
            if self.mode == "safe-only":
                safe_whitelist = [
                    "trailing whitespace", "W291", "W293",
                    "__init__.py", "docs/ directory",
                    "No docs/ directory",
                ]
                if not any(w in msg for w in safe_whitelist):
                    change.status = "skipped"
                    change.reason = "Not in safe-only whitelist"
                    self.skipped.append(change)
                    return "skipped (safe-only whitelist)"

            # ── Backup ──
            if change.file and (self.workspace / change.file).exists():
                fp = self.workspace / change.file
                bp = self.safety.create_backup(fp)
                if bp:
                    self.backup_paths.append(bp)
                    change.backup_path = bp

            # ── Preview via patch_preview.py ──
            if change.file:
                fp = self.workspace / change.file
                if fp.exists():
                    preview_script = TOOLCASE_DIR / "patch_preview.py"
                    if preview_script.exists():
                        subprocess.run(
                            [sys.executable, str(preview_script), str(fp)],
                            timeout=10,
                        )

            # ── Execute the actual fix ──
            fixed = False

            # Trailing whitespace (W291: trailing ws, W293: blank line ws)
            if "W291" in msg or "W293" in msg or "trailing" in msg.lower():
                if change.file:
                    fp = self.workspace / change.file
                    if fp.exists():
                        fixed = self._fix_trailing_whitespace(fp, change)

            # Missing __init__.py
            elif "Missing __init__.py" in msg and change.file == "":
                # Extract directory name from message
                import re as _re
                m = _re.search(r"in (\S+)/$", msg)
                if m:
                    dirname = m.group(1)
                    dirpath = self.workspace / dirname
                    if dirpath.is_dir():
                        fixed = self._create_init_py(dirpath, change)

            # Missing docs/ directory
            elif "No docs/ directory" in msg or "docs/ directory" in msg:
                fixed = self._create_docs_dir(change)

            # Unknown safe change — log as skipped with explanation
            else:
                change.status = "skipped"
                change.reason = "Auto-fix not implemented for this finding type"
                self.skipped.append(change)
                return "skipped (no auto-fix)"

            if fixed:
                change.status = "applied"
                self.applied.append(change)
                return "applied"
            else:
                # Attempted but nothing changed or failed
                change.status = "skipped"
                change.reason = change.reason or "No fix needed or could not apply"
                self.skipped.append(change)
                return "skipped (no fix needed)"

        return "unknown"

    def rollback_all(self) -> list[str]:
        """Roll back all applied changes."""
        rolled = []
        for c in self.applied:
            if c.file:
                fp = self.workspace / c.file
                if self.safety.rollback(fp):
                    c.status = "rolled_back"
                    rolled.append(c.file)
        return rolled


# ── Test Runner ──────────────────────────────────────────────

class TestRunner:
    """Runs compile checks and optionally tool tests."""

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def run(self, focus: str = "all") -> dict:
        result = {"status": "passed", "command": None, "details": [],
                  "exit_code": 0}

        # Python compile check
        compile_cmd = f"python -m py_compile"
        result["command"] = f"{compile_cmd} *.py"
        errors = []
        for pyfile in sorted(self.workspace.glob("*.py")):
            r = subprocess.run(
                [sys.executable, "-m", "py_compile", str(pyfile)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if r.returncode != 0:
                err = r.stderr.strip()[:80]
                errors.append(f"{pyfile.name}: {err}")
                result["details"].append(f"❌ {pyfile.name}: {err}")

        if errors:
            result["status"] = "failed"
            result["exit_code"] = 2
        else:
            py_count = len(list(self.workspace.glob("*.py")))
            result["details"].append(f"✅ All {py_count} .py files compile OK")

        # Check for test_runner.py
        if focus in ("all", "tests"):
            test_script = self.workspace / "test_runner.py"
            if test_script.exists():
                r = subprocess.run(
                    [sys.executable, str(test_script), str(self.workspace)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                )
                if r.returncode == 0:
                    result["details"].append("✅ test_runner.py: all tests passed")
                else:
                    result["status"] = "warning"
                    result["details"].append(f"⚠  test_runner: exit {r.returncode}")
                    if not result["exit_code"]:
                        result["exit_code"] = 1

        return result


# ── Report Generator ─────────────────────────────────────────

class ReportGenerator:
    """Generates human-readable and JSON reports."""

    def __init__(self, mode: str, focus: str, cycles_executed: int,
                 reports: list[CycleReport]):
        self.mode = mode
        self.focus = focus
        self.cycles_executed = cycles_executed
        self.reports = reports

    def human_report(self) -> str:
        """Generate the formatted report."""
        lines = []
        lines.append("")
        lines.append("# Self Improve Report")
        lines.append("")
        lines.append(f"## Mode")
        lines.append(f"{self.mode}")
        lines.append("")
        lines.append(f"## Cycles")
        lines.append(f"{self.cycles_executed}")
        lines.append("")

        all_findings = []
        all_planned = []
        all_applied = []
        all_skipped = []
        all_backups = []
        final_tests = {"status": "not_run"}
        rollback_executed = False
        rollback_reason = None

        for rep in self.reports:
            all_findings.extend(rep.findings)
            all_planned.extend(rep.planned_improvements)
            all_applied.extend(rep.applied_changes)
            all_skipped.extend(rep.skipped_changes)
            all_backups.extend(rep.backup_paths)
            if rep.tests.get("status") != "not_run":
                final_tests = rep.tests
            if rep.rollback.get("executed"):
                rollback_executed = True
                rollback_reason = rep.rollback.get("reason")

        # Summary
        critical = sum(1 for f in all_findings if f.severity == "critical")
        high = sum(1 for f in all_findings if f.severity == "high")
        medium = sum(1 for f in all_findings if f.severity == "medium")
        low = sum(1 for f in all_findings if f.severity in ("low", "info"))

        total_status = "passed"
        if rollback_executed:
            total_status = "rolled_back"
        elif final_tests.get("status") == "failed":
            total_status = "failed"
        elif critical > 0 or high > 0 or medium > 0:
            total_status = "warning"

        lines.append("## Summary")
        lines.append(f"Status: {total_status}")
        lines.append(
            f"Findings: {len(all_findings)} "
            f"({critical} critical, {high} high, "
            f"{medium} medium, {low} low)"
        )
        lines.append(f"Planned: {len(all_planned)}")
        lines.append(f"Applied: {len(all_applied)}")
        lines.append(f"Skipped: {len(all_skipped)}")
        lines.append(f"Backups: {len(all_backups)}")
        lines.append("")

        # Findings by category
        cats = {}
        for f in all_findings:
            cats.setdefault(f.category, []).append(f)
        lines.append("## Findings")
        for cat in ["code-quality", "security", "project-health", "docs", "tests", "build"]:
            if cat in cats:
                lines.append(f"- {cat}: {len(cats[cat])} issues")
                for f in cats[cat][:5]:  # Show top 5
                    sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡",
                                "low": "🔵", "warning": "⚠", "info": "ℹ"}
                    icon = sev_icon.get(f.severity, "•")
                    loc = f" ({f.file}:{f.line})" if f.file else ""
                    lines.append(f"  {icon} [{f.severity}] {f.message[:90]}{loc}")
                if len(cats[cat]) > 5:
                    lines.append(f"  ... and {len(cats[cat]) - 5} more")
        lines.append("")

        # Planned improvements
        lines.append("## Planned Improvements")
        if all_planned:
            for i, c in enumerate(all_planned[:10], 1):
                icon = {"safe": "✅", "needs_approval": "⚠", "forbidden": "⛔"}
                lines.append(f"  {i}. {icon.get(c.category, '•')} {c.description[:90]}")
                if c.category == "forbidden":
                    lines.append(f"     Reason: {c.reason}")
            if len(all_planned) > 10:
                lines.append(f"  ... and {len(all_planned) - 10} more")
        else:
            lines.append("  None planned.")
        lines.append("")

        # Applied changes
        lines.append("## Applied Changes")
        if all_applied:
            for i, c in enumerate(all_applied, 1):
                lines.append(f"  {i}. ✅ {c.description[:90]}")
        else:
            lines.append("  No changes applied.")
        lines.append("")

        # Skipped changes
        lines.append("## Skipped Changes")
        if all_skipped:
            for i, c in enumerate(all_skipped, 1):
                lines.append(f"  {i}. ⏭️  {c.description[:80]}")
                lines.append(f"     Reason: {c.reason or 'Not applicable in this mode'}")
        else:
            lines.append("  None skipped.")
        lines.append("")

        # Backup
        lines.append("## Backup")
        if all_backups:
            for bp in all_backups[:5]:
                lines.append(f"  {Path(bp).name}")
        else:
            lines.append("  No backups created.")
        lines.append("")

        # Test result
        lines.append("## Test Result")
        lines.append(f"  {final_tests.get('status', 'not_run').upper()}")
        for detail in final_tests.get("details", []):
            lines.append(f"  {detail}")
        lines.append("")

        # Rollback
        lines.append("## Rollback")
        if rollback_executed:
            lines.append(f"  Executed: {rollback_reason or 'Unknown reason'}")
        else:
            lines.append("  Not needed.")
        lines.append("")

        # Next recommended step
        lines.append("## Next Recommended Step")
        if rollback_executed:
            lines.append("  1. Check rollback logs and fix the root cause")
            lines.append("  2. Run with --dry-run to verify fixes")
            lines.append("  3. Run again with --apply")
        elif final_tests.get("status") == "failed":
            lines.append("  1. Fix the compile errors listed above")
            lines.append("  2. Run `python -m py_compile <file>` on failing files")
            lines.append("  3. Run `python self_improve_loop.py . --dry-run` again")
        elif all_skipped:
            lines.append(f"  1. {len(all_skipped)} changes were skipped — review reasons above")
            approv = [c for c in all_skipped if c.category == "needs_approval"]
            if approv:
                lines.append("  2. For changes needing approval, run with --apply")
        else:
            lines.append("  ✅ No issues found. Project is healthy.")
        lines.append("")

        return "\n".join(lines)

    def json_report(self) -> dict:
        """Generate machine-readable JSON report."""
        all_findings = []
        all_applied = []
        all_skipped = []
        all_backups = []
        final_tests = {"status": "not_run", "command": None}
        rollback_executed = False
        rollback_reason = None

        for rep in self.reports:
            for f in rep.findings:
                all_findings.append(asdict(f))
            for c in rep.applied_changes:
                all_applied.append(asdict(c))
            for c in rep.skipped_changes:
                all_skipped.append(asdict(c))
            all_backups.extend(rep.backup_paths)
            if rep.tests.get("status") != "not_run":
                final_tests = rep.tests
            if rep.rollback.get("executed"):
                rollback_executed = True
                rollback_reason = rep.rollback.get("reason")

        total_status = "passed"
        if rollback_executed:
            total_status = "rolled_back"
        elif final_tests.get("status") == "failed":
            total_status = "failed"
        elif any(
            f.severity in ("critical", "high", "medium")
            for rep in self.reports
            for f in rep.findings
        ):
            total_status = "warning"

        return {
            "status": total_status,
            "mode": self.mode,
            "focus": self.focus,
            "cycles": self.cycles_executed,
            "findings": all_findings,
            "planned_improvements": [],
            "applied_changes": all_applied,
            "skipped_changes": all_skipped,
            "backup_path": all_backups[0] if all_backups else None,
            "tests": final_tests,
            "rollback": {
                "executed": rollback_executed,
                "reason": rollback_reason,
            },
        }


# ── Orchestrator ─────────────────────────────────────────────

def run_one_cycle(
    cycle: int, total_cycles: int,
    safety: SafetyManager, workspace: Path,
    mode: str, focus: str,
) -> CycleReport:
    """Run one self-improvement cycle."""
    report = CycleReport(cycle=cycle, mode=mode, focus=focus)

    print(f"\n{'─'*60}")
    print(f"  Cycle {cycle}/{total_cycles} — Mode: {mode}  Focus: {focus}")
    print(f"{'─'*60}")

    # Step 1-5: Scan
    print("\n  🔍 Scanning...")
    scanner = CodeScanner(workspace, focus)
    findings = scanner.scan_all()
    report.findings = findings
    print(f"     {len(findings)} finding(s)")

    # Step 6: Plan
    print("\n  📋 Planning...")
    planner = ImprovementPlanner(safety, mode)
    changes = planner.plan(findings)
    report.planned_improvements = changes

    safe_count = sum(1 for c in changes if c.category == "safe")
    approval_count = sum(1 for c in changes if c.category == "needs_approval")
    forbidden_count = sum(1 for c in changes if c.category == "forbidden")
    print(f"     {safe_count} safe, {approval_count} need approval, {forbidden_count} forbidden")

    # Report findings by severity
    critical = [f for f in findings if f.severity == "critical"]
    high = [f for f in findings if f.severity == "high"]
    if critical:
        report.status = "failed"
        print("     🔴 Critical issues found — will not apply changes")
    elif high:
        if mode == "safe-only":
            report.status = "warning"
        print("     🟠 High severity issues found")
    elif findings:
        report.status = "warning" if any(f.severity == "medium" for f in findings) else "passed"

    # Blocked by safety
    if forbidden_count > 0:
        for c in changes:
            if c.category == "forbidden":
                report.errors.append(f"BLOCKED: {c.description}")
        report.status = "blocked"

    # Step 7-9: Apply (if mode allows)
    executor = Executor(safety, workspace, mode)

    if mode == "dry-run":
        # Show plan but don't apply
        for c in changes:
            if c.category == "safe":
                report.skipped_changes.append(c)
        print(f"     🏁 Dry-run — no changes applied")
        return report

    if report.status in ("failed", "blocked"):
        print(f"     ⏹  Stopping — no changes applied")
        return report

    if mode in ("safe-only", "apply"):
        changed_any = False
        for c in changes:
            if c.category == "safe" or (c.category == "needs_approval" and mode == "apply"):
                result = executor.apply(c)
                if result == "applied":
                    changed_any = True
                if c.status == "skipped":
                    report.skipped_changes.append(c)

        report.applied_changes = executor.applied
        report.backup_paths = executor.backup_paths
        print(f"     Applied: {len(executor.applied)}, Skipped: {len(executor.skipped)}")

    # Step 10: Test
    if mode in ("safe-only", "apply"):
        print("\n  🧪 Testing...")
        tester = TestRunner(workspace)
        test_result = tester.run(focus)
        report.tests = test_result
        print(f"     Status: {test_result['status']}")

        # Rule 9: Halt on regression
        if test_result["status"] == "failed":
            print("     ⛔ RULE 9: Tests/build got worse!")
            rolled = executor.rollback_all()
            report.rollback = {"executed": True, "reason": f"Tests failed after changes"}
            report.status = "rolled_back"
            for f in rolled:
                print(f"     ↩  Rolled back: {f}")
            return report

        # Rule 10: Validate
        if test_result["status"] == "warning":
            report.status = "warning"
            report.warnings.append("Test warnings found")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="self_improve_loop.py — Autonomous self-improvement for ToolCase v3.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "CLI commands:\n"
            "  %(prog)s .                        # Default: dry-run, 1 cycle\n"
            "  %(prog)s . --dry-run              # Analyse only\n"
            "  %(prog)s . --cycles 3             # 3 improvement cycles\n"
            "  %(prog)s . --apply                # Apply changes + test + rollback\n"
            "  %(prog)s . --json                 # Machine-readable JSON output\n"
            "  %(prog)s . --safe-only            # Only safe formatting/docs fixes\n"
            "  %(prog)s . --focus docs           # Focus on documentation\n"
            "  %(prog)s . --focus security       # Focus on security\n"
            "  %(prog)s . --focus code-quality   # Focus on code quality\n"
            "  %(prog)s . --focus tests          # Focus on tests\n"
            "\n"
            "Exit codes:\n"
            "  0  No problems found\n"
            "  1  Warnings found\n"
            "  2  Errors or tests failed\n"
            "  3  Rollback executed\n"
            "  4  Blocked by safety rule\n"
        ),
    )
    parser.add_argument("target", nargs="?", default=".",
                        help="Workspace path (default: current directory)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Analyse only — no files modified, show plan")
    parser.add_argument("--apply", action="store_true",
                        help="Apply mode — backup, preview, test, rollback on failure")
    parser.add_argument("--safe-only", action="store_true",
                        help="Only trailing whitespace, formatting, docs, __init__.py fixes")
    parser.add_argument("--cycles", type=int, default=1,
                        help=f"Number of improvement cycles (max {MAX_CYCLES_LIMIT})")
    parser.add_argument("--json", action="store_true",
                        help="Output machine-readable JSON")
    parser.add_argument("--focus", choices=["all", "docs", "security", "code-quality", "tests"],
                        default="all",
                        help="Focus scanning on a specific area")

    args = parser.parse_args()

    # ── Determine mode ──
    if args.apply:
        mode = "apply"
    elif args.safe_only:
        mode = "safe-only"
    elif args.dry_run:
        mode = "dry-run"
    else:
        mode = "dry-run"  # Default

    # ── Cycles limit ──
    cycles = min(args.cycles, MAX_CYCLES_LIMIT)
    if args.cycles > MAX_CYCLES_LIMIT:
        print(f"⚠  Cycles capped at {MAX_CYCLES_LIMIT} (was {args.cycles})")

    # ── Resolve workspace ──
    workspace = Path(args.target).resolve()
    if not workspace.exists():
        print(f"❌ Target does not exist: {workspace}")
        sys.exit(2)
    if not workspace.is_dir():
        workspace = workspace.parent

    # ── Init ──
    safety = SafetyManager(workspace)
    reports: list[CycleReport] = []
    final_exit = 0

    print(f"\n{'='*60}")
    print(f" ♻️  ToolCase Self-Improve Loop")
    print(f"{'='*60}")
    print(f" Workspace: {workspace}")
    print(f" Mode:      {mode}")
    print(f" Focus:     {args.focus}")
    print(f" Cycles:    {cycles}")

    # ── Run cycles ──
    try:
        for cycle in range(1, cycles + 1):
            report = run_one_cycle(
                cycle=cycle, total_cycles=cycles,
                safety=safety, workspace=workspace,
                mode=mode, focus=args.focus,
            )
            reports.append(report)

            # Stop on rollback or block
            if report.status in ("rolled_back", "blocked"):
                print(f"\n  ⏹  Stopping — cycle {cycle} ended with status: {report.status}")
                break

            # Stop if clean in safe-only mode
            if mode == "safe-only" and report.status == "passed" and not report.applied_changes:
                if cycle < cycles:
                    print(f"\n  ✅ Clean — no further cycles needed")
                break

    except KeyboardInterrupt:
        print("\n\n⚠  Interrupted by user")
        final_exit = 1

    # ── Generate report ──
    generator = ReportGenerator(
        mode=mode, focus=args.focus,
        cycles_executed=len(reports),
        reports=reports,
    )

    if args.json:
        output = generator.json_report()
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    else:
        output = generator.human_report()
        print(output)

    # ── Save report to file ──
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = "json" if args.json else "txt"
    report_path = REPORT_DIR / f"self_improve_{ts}.{ext}"
    if args.json:
        report_path.write_text(json.dumps(
            generator.json_report(), indent=2, ensure_ascii=False, default=str
        ), encoding="utf-8")
    else:
        report_path.write_text(output, encoding="utf-8")
    print(f"\n📄 Report saved: {report_path}")

    # ── Determine exit code ──
    for rep in reports:
        ec = rep.final_exit_code()
        if ec > final_exit:
            final_exit = ec

    sys.exit(final_exit)


if __name__ == "__main__":
    main()
