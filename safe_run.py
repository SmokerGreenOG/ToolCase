#!/usr/bin/env python3
"""
safe_run.py — Central safe subprocess executor for ToolCase v5.4.1.

Drop-in replacement for subprocess.run() that enforces:
  1. Workspace containment — commands must target files within workspace
  2. Shell/interpreter detection — blocks `python -c`, `bash -c`, `powershell -Command`
  3. PowerShell encoded command blocking
  4. Destructive Docker/Git/package-manager/filesystem command detection
  5. Allowlisted executables (optional)
  6. Approval enforcement based on risk metadata
  7. Execution logging

API:
    safe_run(cmd, workspace=None, risk_level="medium", approval_required=False, **kwargs)
    classify_command(cmd) -> dict
    is_within_workspace(target, workspace) -> bool

Usage:
    # As Python API (preferred)
    from safe_run import safe_run, Risk
    result = safe_run(["git", "status"], workspace="/project")

    # As CLI guard
    python safe_run.py check "rm -rf /"
    python safe_run.py check "docker system prune -af" --json
"""

__maker__ = "SmokerGreenOG"

import _protect

import argparse
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Risk levels
# ---------------------------------------------------------------------------


class Risk(IntEnum):
    SAFE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    BLOCKED = 4


RISK_LABELS: dict[Risk, str] = {
    Risk.SAFE: "safe",
    Risk.LOW: "low",
    Risk.MEDIUM: "medium",
    Risk.HIGH: "high",
    Risk.BLOCKED: "blocked",
}

RISK_ICONS: dict[Risk, str] = {
    Risk.SAFE: "\U0001f7e2",
    Risk.LOW: "\U0001f7e1",
    Risk.MEDIUM: "\U0001f7e0",
    Risk.HIGH: "\U0001f534",
    Risk.BLOCKED: "\u274c",
}

# Exit codes for CLI mode
EXIT_OK = 0
EXIT_WARNING = 1
EXIT_DANGEROUS = 2
EXIT_ERROR = 3

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FILE = Path(__file__).parent / ".safe_run.log"

_log: logging.Logger | None = None  # Lazy init — no file write on import


def _get_log() -> logging.Logger:
    """Lazy-init the audit log. No file writes until first safe_run() call."""
    global _log
    if _log is not None:
        return _log
    
    # Use a user-writable location, not site-packages
    log_dir = Path.home() / ".toolcase" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger("safe_run")
    logger.setLevel(logging.INFO)
    
    handler = logging.FileHandler(str(log_dir / "safe_run.log"), encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)
    logger.propagate = False
    
    _log = logger
    return logger


def _mask_secrets(cmd_str: str) -> str:
    """Mask potential secrets in command strings before logging."""
    # Mask --token, --password, --api-key style args
    masked = re.sub(r'(--\w*(?:token|password|secret|key|auth)\w*)\s+\S+', r'\1 ***', cmd_str, flags=re.IGNORECASE)
    # Mask KEY=VALUE style
    masked = re.sub(r'(\w*(?:TOKEN|PASSWORD|SECRET|KEY|AUTH)\w*)=\S+', r'\1=***', masked, flags=re.IGNORECASE)
    return masked

# Well-known system executables exempt from workspace containment
_SYSTEM_EXECUTABLES: frozenset[str] = frozenset({
    "python", "python3", "python3.11", "python3.12", "python3.13",
    "python.exe", "python3.exe", "pythonw.exe",
    "git", "git.exe", "docker", "docker.exe",
    "bash", "sh", "zsh", "node", "node.exe",
    "npm", "npx", "pip", "pip3", "cargo",
    "make", "cmake", "gcc", "g++", "clang",
})

# Build set of resolved paths for known system executables
def _build_resolved_allowlist() -> frozenset[str]:
    """Resolve known executables via PATH and sys.executable."""
    resolved = set()
    # Always trust the current Python interpreter
    resolved.add(str(Path(sys.executable).resolve()))
    for exe in _SYSTEM_EXECUTABLES:
        found = shutil.which(exe)
        if found:
            resolved.add(str(Path(found).resolve()))
    return frozenset(resolved)

_RESOLVED_SYSTEM_PATHS: frozenset[str] = _build_resolved_allowlist()

# ---------------------------------------------------------------------------
# Command pattern database
# ---------------------------------------------------------------------------


@dataclass
class CommandPattern:
    """A detection pattern for command classification."""
    regex: re.Pattern
    risk: Risk
    reason: str
    safe_alternative: str = ""


# ── BLOCKED: Never allow these ─────────────────────────────

BLOCKED_PATTERNS: list[CommandPattern] = [
    CommandPattern(
        re.compile(
            r'(?:rm|del|erase)\s+(?:-[rR][fF]|-[fF][rR]|/[sS][fFqQ]?)\s+/(?:\s|$)'
            r'|(?:rm|del)\s+(?:-[rR][fF]|/[sS][fFqQ]?)\s+(?:--no-preserve-root|/\*|C:\\)'
        ),
        Risk.BLOCKED,
        "Recursive delete on root filesystem — would destroy the entire system.",
        "Never run recursive delete on / or C:\\.",
    ),
    CommandPattern(
        re.compile(
            r'\b(?:format|mkfs\.\w+)\s+(?:c:|/dev/)',
        ),
        Risk.BLOCKED,
        "Disk format — would destroy all data on a drive.",
        "",
    ),
    CommandPattern(
        re.compile(
            r'>\s*(?:/dev/sd[a-z]|/dev/nvme|/dev/mmcblk|/dev/disk)',
        ),
        Risk.BLOCKED,
        "Output redirection to raw block device — would corrupt partition table.",
        "Redirect to a regular file instead.",
    ),
]

# ── HIGH: Destructive but potentially legitimate ───────────

HIGH_PATTERNS: list[CommandPattern] = [
    CommandPattern(
        re.compile(
            r'\brm\s+(?:-[rR][fF]|-[fF][rR])'
            r'|del\s+/[sS][fFqQ]?'
            r'|rmdir\s+/[sS]'
        ),
        Risk.HIGH,
        "Recursive force delete — permanently removes files without confirmation.",
        "Use 'rm -ri' (interactive) or move files to trash first.",
    ),
    CommandPattern(
        re.compile(
            r'\bdd\s+if=.*\s+of=',
        ),
        Risk.HIGH,
        "dd (disk destroyer) — can overwrite arbitrary disk blocks.",
        "Double-check the 'of=' target. Use 'cp' for file copies.",
    ),
    CommandPattern(
        re.compile(
            r'(?:curl|wget)\s+.*?\|\s*(?:sh|bash|zsh)\b',
        ),
        Risk.HIGH,
        "Shell pipe from network — downloads and immediately executes remote script.",
        "Download first, inspect, then run: curl -o script.sh <url> && bash script.sh",
    ),
    CommandPattern(
        re.compile(
            r'\bgit\s+clean\s+-[fF][dDxX]',
        ),
        Risk.HIGH,
        "Destructive git clean — removes untracked files and directories.",
        "Use 'git clean -n' to preview first.",
    ),
    CommandPattern(
        re.compile(
            r'\bgit\s+reset\s+--hard\b',
        ),
        Risk.HIGH,
        "Hard git reset — discards all uncommitted changes.",
        "Use 'git stash' first to save changes.",
    ),
    CommandPattern(
        re.compile(
            r'\bgit\s+push\s+.*?--force\b(?!-with-lease)',
        ),
        Risk.HIGH,
        "Force git push — overwrites remote history.",
        "Use 'git push --force-with-lease' instead.",
    ),
    CommandPattern(
        re.compile(
            r'\bdocker\s+(?:system\s+prune|container\s+prune|image\s+prune|volume\s+prune)\b',
        ),
        Risk.HIGH,
        "Docker prune — permanently removes containers/images/volumes.",
        "Use 'docker system df' to check space first. Add '--filter' to be selective.",
    ),
    CommandPattern(
        re.compile(
            r'\bdocker\s+rm\s+-f\b',
        ),
        Risk.HIGH,
        "Docker force-remove — kills and removes running containers.",
        "Use 'docker stop' first, then 'docker rm'.",
    ),
    CommandPattern(
        re.compile(
            r'\bchmod\s+(?:-R\s+)?777\b',
        ),
        Risk.HIGH,
        "World-writable permissions — grants everyone read/write/execute.",
        "Use 'chmod 755' for dirs, 'chmod 644' for files.",
    ),
    CommandPattern(
        re.compile(
            r'\bchown\s+-[Rr]\s+\S+\s+/',
        ),
        Risk.HIGH,
        "Recursive chown on system path — changes ownership broadly.",
        "Target specific paths, not / or /etc.",
    ),
]

# ── MEDIUM: Potentially risky ─────────────────────────────

MEDIUM_PATTERNS: list[CommandPattern] = [
    CommandPattern(
        re.compile(
            r'(?:pip|pip3)\s+install\s+.*?(?:https?://|git\+)',
        ),
        Risk.MEDIUM,
        "pip install from URL — could install malicious code.",
        "Use PyPI: 'pip install <package>'. Pin versions with hashes.",
    ),
    CommandPattern(
        re.compile(
            r'\bnpm\s+(?:install|ci)\s+.*?--unsafe-perm',
        ),
        Risk.MEDIUM,
        "npm install --unsafe-perm — runs scripts as root.",
        "Avoid --unsafe-perm. Use regular 'npm install'.",
    ),
    CommandPattern(
        re.compile(
            r'\bgit\s+push\s+--force-with-lease\b',
        ),
        Risk.MEDIUM,
        "Force-with-lease git push — safer than --force but still rewrites history.",
        "Coordinate with collaborators before force-pushing.",
    ),
    CommandPattern(
        re.compile(
            r'\b(?:shutdown|reboot|poweroff|halt)\b',
        ),
        Risk.MEDIUM,
        "System shutdown/reboot — terminates all running processes.",
        "Notify users first. Use 'shutdown -c' to cancel.",
    ),
    CommandPattern(
        re.compile(
            r'\beval\s+\$?\(',
        ),
        Risk.MEDIUM,
        "Dynamic command evaluation — enables injection attacks.",
        "Avoid eval. Use proper quoting and arrays.",
    ),
    CommandPattern(
        re.compile(
            r'\bcomposer\s+(?:update|require)\b',
        ),
        Risk.MEDIUM,
        "Composer update/require — modifies dependencies.",
        "Run 'composer outdated' first. Commit lock file changes.",
    ),
]

# ── SHELL/INTERPRETER: Python -c, bash -c, etc. ──────────

SHELL_INTERPRETER_PATTERNS: list[CommandPattern] = [
    CommandPattern(
        re.compile(
            r'\bpython[23]?(?:\.exe)?\s+-c\s+\S',
            re.IGNORECASE,
        ),
        Risk.HIGH,
        "Python inline code execution — runs arbitrary Python code from command line.",
        "Write to a .py file, review it, then run: python script.py",
    ),
    CommandPattern(
        re.compile(
            r'\bbash\s+-c\s+\S',
        ),
        Risk.HIGH,
        "Bash inline command — runs arbitrary shell code.",
        "Write to a .sh file, review, then run: bash script.sh",
    ),
    CommandPattern(
        re.compile(
            r'\bsh\s+-c\s+\S',
        ),
        Risk.HIGH,
        "Shell inline command — runs arbitrary shell code.",
        "Write to a .sh file, review, then run.",
    ),
    CommandPattern(
        re.compile(
            r'\b(?:ruby|perl|node|php)(?:\.exe)?\s+-[cer]\s+\S',
            re.IGNORECASE,
        ),
        Risk.HIGH,
        "Interpreter inline code — runs arbitrary code from command line.",
        "Write to a file, review, then run the interpreter on the file.",
    ),
    CommandPattern(
        re.compile(
            r'\b(?:powershell|pwsh)(?:\.exe)?\s+-(?:Command|c|File)\s+',
            re.IGNORECASE,
        ),
        Risk.HIGH,
        "PowerShell inline execution — runs arbitrary PowerShell code.",
        "Write to a .ps1 file, review, then run: powershell -File script.ps1",
    ),
    CommandPattern(
        re.compile(
            r'\bcmd(?:\.exe)?\s+/c\s+',
            re.IGNORECASE,
        ),
        Risk.HIGH,
        "cmd.exe inline command — runs arbitrary Windows shell commands.",
        "Avoid cmd /c; use direct executable calls instead.",
    ),
]

# ── Interpreter executables + flags (argv-token based, catches full Windows paths) ──

# Normalised basenames (no .exe, no path) of interpreters that can run inline code.
_INTERPRETER_EXECUTABLES: frozenset[str] = frozenset({
    "python", "python3", "python2",
    "bash", "sh", "zsh", "dash",
    "ruby", "perl", "node", "php",
    "powershell", "pwsh",
    "cmd",
})

# Flags that indicate inline code execution (not running a script file).
_INTERPRETER_CODE_FLAGS: frozenset[str] = frozenset({
    "-c", "-e", "-r", "-Command", "-EncodedCommand", "/c", "/C",
})

def _is_shell_interpreter_cmd(cmd_list: list[str]) -> bool:
    """Check if a command list invokes a shell/interpreter with inline code flags.

    Works on the raw argv tokens, normalising argv[0] to basename without .exe
    so that ``C:\\Python311\\python.exe -c "..."`` is caught identically to
    ``python -c "..."``.
    """
    if not cmd_list:
        return False
    exe_path = cmd_list[0]
    exe_name = Path(exe_path).name.lower()
    # Strip .exe extension for comparison
    if exe_name.endswith(".exe"):
        exe_name = exe_name[:-4]
    if exe_name not in _INTERPRETER_EXECUTABLES:
        return False
    # Check for inline-code flags in remaining args (case-insensitive)
    for arg in cmd_list[1:]:
        arg_lower = arg.lower()
        # Exact match against known flags
        if arg_lower in _INTERPRETER_CODE_FLAGS:
            return True
        # Handle combined form: -c"...", /c"..."
        if len(arg_lower) > 2 and arg_lower[:2] in _INTERPRETER_CODE_FLAGS:
            return True
        # Handle --EncodedCommand=... form
        if '=' in arg_lower:
            flag = arg_lower.split('=', 1)[0]
            if flag in _INTERPRETER_CODE_FLAGS:
                return True
    return False

# ── ENCODED COMMANDS: Base64, hex, etc. ───────────────────

ENCODED_COMMAND_PATTERNS: list[CommandPattern] = [
    CommandPattern(
        re.compile(
            r'\b(?:powershell|pwsh)\s+.*?(?:-EncodedCommand|-enc|-e)\s+\S',
            re.IGNORECASE,
        ),
        Risk.BLOCKED,
        "PowerShell encoded command — obfuscated command that bypasses inspection.",
        "Decode the command first: [System.Text.Encoding]::Unicode.GetString([System.Convert]::FromBase64String('...'))",
    ),
    CommandPattern(
        re.compile(
            r'\bcmd\s+/c\s+.*?(?:echo|type).*?\|.*?\b(?:powershell|pwsh)\b',
            re.IGNORECASE,
        ),
        Risk.BLOCKED,
        "cmd piping to PowerShell — potential obfuscation pattern.",
        "",
    ),
    CommandPattern(
        re.compile(
            r'\b(?:bash|sh)\s+<<<\s*\$\(echo\s+',
        ),
        Risk.BLOCKED,
        "Base64-decoded bash execution — obfuscated command.",
        "",
    ),
]

# ── SAFE: Known-safe patterns ─────────────────────────────

SAFE_PATTERNS: list[CommandPattern] = [
    CommandPattern(
        re.compile(r'^(?:ls|dir)\b'),
        Risk.SAFE,
        "List directory contents — read-only.",
        "",
    ),
    CommandPattern(
        re.compile(r'^(?:cd|pwd|chdir)\b'),
        Risk.SAFE,
        "Navigation — no destructive potential.",
        "",
    ),
    CommandPattern(
        re.compile(r'^(?:cat|type|head|tail)\s+\S'),
        Risk.SAFE,
        "Display file contents — read-only.",
        "",
    ),
    CommandPattern(
        re.compile(r'^grep\b'),
        Risk.SAFE,
        "Text search — read-only.",
        "",
    ),
    CommandPattern(
        re.compile(r'^git\s+(?:status|log|diff|branch|stash\s+list)\b'),
        Risk.SAFE,
        "Git read operations — no modifications.",
        "",
    ),
    CommandPattern(
        re.compile(r'^git\s+(?:add|commit)\b'),
        Risk.LOW,
        "Git stage/commit — local modifications only.",
        "Review staged changes with 'git diff --staged' before committing.",
    ),
    CommandPattern(
        re.compile(r'^git\s+checkout\s+(?!-b)'),
        Risk.LOW,
        "Git checkout — switches branches, may overwrite local changes.",
        "Stash or commit changes before switching branches.",
    ),
    CommandPattern(
        re.compile(r'^docker\s+ps\b'),
        Risk.SAFE,
        "Docker list containers — read-only.",
        "",
    ),
    CommandPattern(
        re.compile(r'^docker\s+(?:images|logs|inspect|stats)\b'),
        Risk.SAFE,
        "Docker info — read-only.",
        "",
    ),
    CommandPattern(
        re.compile(r'^(?:echo|printf|print)\b'),
        Risk.SAFE,
        "Print output — no side effects.",
        "",
    ),
    CommandPattern(
        re.compile(r'^python[23]?\s+\S+\.py\b'),
        Risk.LOW,
        "Run Python script — review the script before executing.",
        "Review scripts from untrusted sources before running.",
    ),
]


# ── All patterns in priority order ────────────────────────

ALL_PATTERNS: list[CommandPattern] = (
    BLOCKED_PATTERNS
    + ENCODED_COMMAND_PATTERNS
    + SHELL_INTERPRETER_PATTERNS
    + HIGH_PATTERNS
    + MEDIUM_PATTERNS
    + SAFE_PATTERNS
)

# ---------------------------------------------------------------------------
# Workspace containment
# ---------------------------------------------------------------------------


def resolve_workspace(workspace: str | Path | None) -> Path | None:
    """Resolve workspace path. None = no containment."""
    if workspace is None:
        return None
    return Path(workspace).resolve()


def is_within_workspace(target: str | Path, workspace: str | Path) -> bool:
    """Check if target path is within the workspace."""
    try:
        Path(target).resolve().relative_to(Path(workspace).resolve())
        return True
    except ValueError:
        return False


def _extract_paths_from_command(cmd: list[str] | str) -> list[str]:
    """Extract potential file/directory paths from a command.

    Includes the executable, option values with =, positional args,
    and bare relative filenames (resolved by caller against cwd).
    """
    if isinstance(cmd, str):
        parts = shlex.split(cmd)
    else:
        parts = list(cmd)

    # Flags whose next argument is NOT a file path
    _CODE_FLAGS = frozenset({"-c", "-e", "-m", "--command", "-Command", "-EncodedCommand", "-enc"})

    paths = []
    # Always include the executable (argv[0]) — must be checked against workspace
    if parts:
        paths.append(parts[0])

    skip_next = False
    for part in parts[1:]:  # Skip executable, already added
        if skip_next:
            skip_next = False
            continue
        if part in _CODE_FLAGS or part.startswith("-EncodedCommand"):
            skip_next = True
            continue
        # Extract paths from --flag=value syntax
        if part.startswith("--") and "=" in part:
            _, value = part.split("=", 1)
            if value:
                paths.append(value)
            continue
        # Skip other flags
        if part.startswith("-"):
            continue
        # Heuristic: paths contain / or \\ or start with .
        if "/" in part or "\\" in part or part.startswith("."):
            paths.append(part)
        # Absolute Windows paths
        elif len(part) >= 2 and part[1] == ":":
            paths.append(part)
        # Bare relative filename: resolve against cwd (caller handles this)
        elif "." in part or part.endswith(".py") or part.endswith(".sh"):
            paths.append(part)

    return paths


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


@dataclass
class ClassificationResult:
    """Result of command classification."""
    command: str
    risk: Risk
    risk_label: str
    reason: str = ""
    safe_alternative: str = ""
    matched_pattern: str = ""
    blocked: bool = False

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "risk": self.risk_label,
            "risk_level": int(self.risk),
            "reason": self.reason,
            "safe_alternative": self.safe_alternative,
            "matched_pattern": self.matched_pattern,
            "blocked": self.blocked,
        }


def classify_command(command: str | list[str]) -> ClassificationResult:
    """Classify a command and return its risk level.

    Args:
        command: String or list of strings (subprocess-style).

    Returns:
        ClassificationResult with risk assessment.
    """
    if isinstance(command, list):
        cmd_str = " ".join(shlex.quote(str(p)) for p in command)
    else:
        cmd_str = str(command)

    cmd_lower = cmd_str.lower().strip()

    result = ClassificationResult(
        command=cmd_str,
        risk=Risk.SAFE,
        risk_label="safe",
    )

    if not cmd_lower:
        result.reason = "Empty command."
        return result

    highest_risk: Risk | None = None

    for pattern_def in ALL_PATTERNS:
        # Always search on lowercased command for case-insensitive matching
        match = pattern_def.regex.search(cmd_lower)
        if not match and cmd_lower != cmd_str:
            # Fallback: try original-case for patterns that need it
            match = pattern_def.regex.search(cmd_str)
        if match:
            if highest_risk is None or pattern_def.risk > highest_risk:
                highest_risk = pattern_def.risk
                result.risk = pattern_def.risk
                result.risk_label = RISK_LABELS[pattern_def.risk]
                result.reason = pattern_def.reason
                result.safe_alternative = pattern_def.safe_alternative
                result.matched_pattern = match.group()
                result.blocked = (pattern_def.risk == Risk.BLOCKED)

    # Unknown commands: classify as MEDIUM risk
    if highest_risk is None:
        result.risk = Risk.MEDIUM
        result.risk_label = "medium"
        result.reason = (
            "Unknown command — could not classify. Review manually before executing."
        )

    return result


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------


@dataclass
class SafeRunResult:
    """Wraps subprocess.CompletedProcess with safety metadata."""
    returncode: int
    stdout: str = ""
    stderr: str = ""
    classification: ClassificationResult | None = None
    approved: bool = False
    blocked: bool = False
    block_reason: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.blocked


def safe_run(
    cmd: list[str] | str,
    *,
    workspace: str | Path | None = None,
    risk_level: str = "medium",
    approval_required: bool | None = None,
    allow_shell_interpreters: bool = False,
    allow_encoded_commands: bool = False,
    timeout: int | None = 300,
    cwd: str | Path | None = None,
    capture_output: bool = True,
    text: bool = True,
    env: dict | None = None,
    **kwargs: Any,
) -> SafeRunResult:
    """Safely execute a subprocess command with guard enforcement.

    Args:
        cmd: Command as list (preferred) or string.
        workspace: If set, command paths and cwd must be within this directory.
        risk_level: Maximum allowed risk ('safe', 'low', 'medium', 'high').
                    'blocked' commands are never allowed.
        approval_required: If True, require explicit approval for >= MEDIUM risk.
                           Default: True when risk_level >= 'medium'.
        allow_shell_interpreters: Allow `python -c`, `bash -c`, etc.
        allow_encoded_commands: Allow PowerShell -EncodedCommand etc.
        timeout: Subprocess timeout in seconds.
        cwd: Working directory for the subprocess. Must be within workspace.
        capture_output: Capture stdout/stderr.
        text: Decode output as text.
        env: Environment variables.
        **kwargs: REJECTED — dangerous kwargs (shell, executable, preexec_fn, etc.)
                  are explicitly blocked. Only safe kwargs are forwarded.

    Returns:
        SafeRunResult with execution output and safety metadata.
    """
    # ── Reject dangerous kwargs ────────────────────────────
    DANGEROUS_KWARGS = frozenset({
        "shell", "executable", "preexec_fn", "start_new_session",
        "pipesize", "pass_fds", "restore_signals",
    })
    dangerous = [k for k in kwargs if k in DANGEROUS_KWARGS]
    if dangerous:
        return SafeRunResult(
            returncode=-1,
            blocked=True,
            block_reason=f"Rejected dangerous kwargs: {', '.join(sorted(dangerous))}",
        )
    # Keep only safe kwargs
    safe_kwargs = {k: v for k, v in kwargs.items() if k not in DANGEROUS_KWARGS}

    # ── Normalise command to list ──────────────────────────
    if isinstance(cmd, str):
        cmd_list = shlex.split(cmd)
    else:
        cmd_list = list(cmd)
    cmd_str = " ".join(shlex.quote(str(p)) for p in cmd_list)

    # ── cwd containment ────────────────────────────────────
    execution_cwd: str | None = str(cwd) if cwd else None
    if workspace is not None:
        ws = resolve_workspace(workspace)
        if cwd is not None:
            cwd_resolved = Path(cwd).resolve()
            if not is_within_workspace(cwd_resolved, ws):
                _get_log().warning("CWD VIOLATION: cwd=%s outside workspace=%s", cwd, ws)
                return SafeRunResult(
                    returncode=-1,
                    blocked=True,
                    block_reason=f"cwd outside workspace: {cwd}",
                )
            effective_cwd = cwd_resolved
        else:
            # Default cwd to workspace — prevents bare-filename bypass
            effective_cwd = ws
        execution_cwd = str(effective_cwd)  # <-- USE THIS for subprocess too
        resolved_paths = []
        for p in _extract_paths_from_command(cmd_list):
            # Only exempt executables found via system PATH, not explicit paths
            # "/tmp/malicious/python" must NOT be exempt just because basename is "python"
            exe_path = Path(p)
            exe_name = exe_path.name.lower()
            is_explicit_path = "/" in p or "\\" in p or (len(p) >= 2 and p[1] == ":")
            if not is_explicit_path and exe_name in _SYSTEM_EXECUTABLES:
                continue
            # Check if resolved explicit path is a known system executable
            resolved = (effective_cwd / p).resolve()
            if str(resolved) in _RESOLVED_SYSTEM_PATHS:
                continue
            resolved_paths.append(str(resolved))
        for p in resolved_paths:
            if not is_within_workspace(p, ws):
                _get_log().warning("WORKSPACE VIOLATION: %s (path=%s)", _mask_secrets(cmd_str), p)
                return SafeRunResult(
                    returncode=-1,
                    blocked=True,
                    block_reason=f"Path outside workspace: {p}",
                )

    # ── Classify ──────────────────────────────────────────
    classification = classify_command(cmd_str)

    # Determine max allowed risk
    max_risk = Risk.SAFE
    for r in Risk:
        if RISK_LABELS[r] == risk_level:
            max_risk = r
            break

    # ── Encoded command: allow if explicitly permitted ──────
    if allow_encoded_commands and classification.risk == Risk.BLOCKED:
        # Check if the only reason it's blocked is an encoded command pattern
        is_encoded = any(
            p.regex.search(classification.command)
            for p in ENCODED_COMMAND_PATTERNS
        )
        if is_encoded:
            # Downgrade from BLOCKED to HIGH — caller accepts the risk
            classification.risk = Risk.HIGH
            classification.risk_label = "high"
            classification.blocked = False

    # ── Shell interpreter: downgrade if explicitly permitted ──
    if allow_shell_interpreters and classification.risk == Risk.HIGH:
        is_interpreter = any(
            p.regex.search(classification.command)
            for p in SHELL_INTERPRETER_PATTERNS
        ) or _is_shell_interpreter_cmd(cmd_list)
        if is_interpreter:
            # Downgrade from HIGH to LOW — caller explicitly accepted the risk.
            # LOW commands skip the approval gate entirely.
            classification.risk = Risk.LOW
            classification.risk_label = "low"

    # ── Block checks ──────────────────────────────────────
    if classification.blocked:
        _get_log().warning("BLOCKED: %s — %s", _mask_secrets(classification.command), classification.reason)
        return SafeRunResult(
            returncode=-1,
            classification=classification,
            blocked=True,
            block_reason=classification.reason,
        )

    if classification.risk == Risk.BLOCKED:
        _get_log().warning("BLOCKED: %s — %s", _mask_secrets(classification.command), classification.reason)
        return SafeRunResult(
            returncode=-1,
            classification=classification,
            blocked=True,
            block_reason=classification.reason,
        )

    # ── Shell interpreter check (regex + argv-token based) ──
    if not allow_shell_interpreters:
        # First: regex patterns on the joined command string
        blocked_by_regex = False
        block_reason_re = ""
        for p in SHELL_INTERPRETER_PATTERNS:
            if p.regex.search(classification.command):
                blocked_by_regex = True
                block_reason_re = p.reason
                break
        # Second: argv-token based check (catches full Windows paths, .exe variants)
        blocked_by_argv = _is_shell_interpreter_cmd(cmd_list)
        if blocked_by_regex or blocked_by_argv:
            reason = block_reason_re or "Shell interpreter with inline code flag detected via argv analysis"
            _get_log().warning("BLOCKED (shell interpreter): %s", classification.command)
            return SafeRunResult(
                returncode=-1,
                classification=classification,
                blocked=True,
                block_reason=f"Shell interpreter execution blocked: {reason}",
            )

    # ── Encoded command check ─────────────────────────────
    if not allow_encoded_commands:
        for p in ENCODED_COMMAND_PATTERNS:
            if p.regex.search(classification.command):
                _get_log().warning("BLOCKED (encoded): %s", classification.command)
                return SafeRunResult(
                    returncode=-1,
                    classification=classification,
                    blocked=True,
                    block_reason=f"Encoded command blocked: {p.reason}",
                )

    # ── Risk level check ──────────────────────────────────
    if classification.risk > max_risk:
        _get_log().warning(
            "RISK EXCEEDED: %s (risk=%s, max=%s)",
            classification.command,
            classification.risk_label,
            risk_level,
        )
        return SafeRunResult(
            returncode=-1,
            classification=classification,
            blocked=True,
            block_reason=(
                f"Risk level {classification.risk_label} exceeds max allowed "
                f"{risk_level}. Reason: {classification.reason}"
            ),
        )

    # ── Workspace containment (already checked above, skip duplicate) ──

    # ── Approval check ────────────────────────────────────
    if approval_required is None:
        approval_required = classification.risk >= Risk.MEDIUM

    if approval_required and classification.risk >= Risk.MEDIUM:
        _get_log().info(
            "APPROVAL REQUIRED: %s (risk=%s)",
            classification.command,
            classification.risk_label,
        )
        return SafeRunResult(
            returncode=-1,
            classification=classification,
            approved=False,
            blocked=True,
            block_reason=(
                f"Approval required for {classification.risk_label}-risk command. "
                f"Reason: {classification.reason}"
            ),
        )

    # ── Execute ───────────────────────────────────────────

    _get_log().info(
        "EXECUTE: %s (risk=%s, workspace=%s)",
        cmd_str,
        classification.risk_label,
        workspace or "none",
    )

    try:
        result = subprocess.run(
            cmd_list,
            timeout=timeout,
            cwd=execution_cwd,
            capture_output=capture_output,
            text=text,
            env=env,
            **safe_kwargs,
        )
        _get_log().info(
            "COMPLETED: %s (exit=%d)",
            cmd_str,
            result.returncode,
        )
        return SafeRunResult(
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            classification=classification,
            approved=True,
        )
    except subprocess.TimeoutExpired as e:
        _get_log().error("TIMEOUT: %s (%ds)", _mask_secrets(cmd_str), timeout or 0)
        return SafeRunResult(
            returncode=-1,
            stderr=f"Command timed out after {timeout}s: {e}",
            classification=classification,
            approved=True,
            blocked=True,
            block_reason=f"Timeout after {timeout}s",
        )
    except FileNotFoundError as e:
        _get_log().error("NOT FOUND: %s — %s", _mask_secrets(cmd_str), e)
        return SafeRunResult(
            returncode=-1,
            stderr=f"Command not found: {cmd_list[0] if cmd_list else cmd_str}",
            classification=classification,
            approved=True,
            blocked=True,
            block_reason=str(e),
        )
    except Exception as e:
        _get_log().error("ERROR: %s — %s", _mask_secrets(cmd_str), e)
        return SafeRunResult(
            returncode=-1,
            stderr=str(e),
            classification=classification,
            approved=True,
            blocked=True,
            block_reason=str(e),
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(
        description="safe_run.py — Central safe subprocess executor for ToolCase.",
    )
    sub = parser.add_subparsers(dest="action", required=True)

    # ── check ─────────────────────────────────────────────
    check = sub.add_parser("check", help="Classify a command without executing.")
    check.add_argument("command", nargs="+", help="Command to classify.")
    check.add_argument("--json", action="store_true", help="Output as JSON.")
    check.add_argument("--verbose", "-v", action="store_true", help="Verbose output.")

    # ── run ───────────────────────────────────────────────
    run = sub.add_parser("run", help="Execute a command with guard enforcement.")
    run.add_argument("command", nargs="+", help="Command to execute.")
    run.add_argument("--workspace", "-w", help="Restrict to workspace directory.")
    run.add_argument("--risk", default="medium",
                     choices=["safe", "low", "medium", "high"],
                     help="Maximum allowed risk level (default: medium).")
    run.add_argument("--approve", action="store_true",
                     help="Approve medium/high risk execution.")
    run.add_argument("--allow-shell", action="store_true",
                     help="Allow shell interpreter execution (python -c, bash -c).")
    run.add_argument("--allow-encoded", action="store_true",
                     help="Allow encoded commands (PowerShell -EncodedCommand).")
    run.add_argument("--timeout", type=int, default=300,
                     help="Timeout in seconds (default: 300).")
    run.add_argument("--json", action="store_true", help="Output as JSON.")

    # ── patterns ──────────────────────────────────────────
    sub.add_parser("patterns", help="List all known dangerous patterns.")

    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.action == "check":
        cmd = " ".join(args.command)
        result = classify_command(cmd)

        if args.json:
            print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        else:
            icon = RISK_ICONS.get(result.risk, "?")
            print(f"\n{icon}  SAFE_RUN — {result.risk_label.upper()}")
            print(f"{'=' * 60}")
            print(f"  Command:    {result.command}")
            print(f"  Risk:       {icon} {result.risk_label}")
            if result.matched_pattern:
                print(f"  Trigger:    {result.matched_pattern}")
            if result.reason:
                print(f"\n  Reason:     {result.reason}")
            if result.safe_alternative:
                print(f"  Alternative: {result.safe_alternative}")
            print()

        if result.risk >= Risk.HIGH:
            return EXIT_DANGEROUS
        elif result.risk >= Risk.MEDIUM:
            return EXIT_WARNING
        return EXIT_OK

    elif args.action == "run":
        cmd = args.command
        workspace = args.workspace

        result = safe_run(
            cmd,
            workspace=workspace,
            risk_level=args.risk,
            approval_required=not args.approve,
            allow_shell_interpreters=args.allow_shell,
            allow_encoded_commands=args.allow_encoded,
            timeout=args.timeout,
        )

        if args.json:
            output = {
                "command": result.classification.command if result.classification else " ".join(cmd),
                "returncode": result.returncode,
                "blocked": result.blocked,
                "block_reason": result.block_reason,
                "risk": result.classification.risk_label if result.classification else "unknown",
                "stdout": result.stdout[:500] if result.stdout else "",
                "stderr": result.stderr[:500] if result.stderr else "",
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            if result.blocked:
                print(f"\n\u274c BLOCKED: {result.block_reason}")
            elif result.ok:
                print(f"\n\u2705 EXECUTED: exit {result.returncode}")
                if result.stdout:
                    print(result.stdout[:1000])
            else:
                print(f"\n\u26a0\ufe0f EXECUTED: exit {result.returncode}")
                if result.stderr:
                    print(result.stderr[:500])

        if result.blocked:
            return EXIT_ERROR
        return EXIT_OK if result.ok else EXIT_DANGEROUS

    elif args.action == "patterns":
        print("\nSAFE_RUN — Known Patterns")
        print("=" * 60)
        categories = [
            ("BLOCKED", BLOCKED_PATTERNS),
            ("ENCODED COMMANDS", ENCODED_COMMAND_PATTERNS),
            ("SHELL INTERPRETERS", SHELL_INTERPRETER_PATTERNS),
            ("HIGH RISK", HIGH_PATTERNS),
            ("MEDIUM RISK", MEDIUM_PATTERNS),
        ]
        for cat_name, patterns in categories:
            print(f"\n  {cat_name}:")
            for p in patterns:
                print(f"    - {p.regex.pattern[:80]}")
                print(f"      {p.reason[:100]}")
        print()

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
