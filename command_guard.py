#!/usr/bin/env python3
"""
command_guard.py — Check terminal commands for safety before execution.

Classifies commands as safe, warning, or dangerous by detecting risky patterns:
  - rm -rf / del /s (recursive deletes)
  - format / mkfs (disk destruction)
  - curl|sh / wget|sh (remote code execution via pipe)
  - PowerShell download+execute patterns
  - Recursive delete commands (rmdir /s, rd /s)
  - Dangerous chmod/chown (777, -R to system paths)
  - git clean -fdx (destructive repo cleanup)
  - npm scripts with suspicious commands
  - pip install from non-pypi URLs

Usage:
    python command_guard.py "rm -rf /"
    python command_guard.py "ls -la" --json
    python command_guard.py "dangerous command" --explain
"""

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Risk pattern definitions
# ---------------------------------------------------------------------------

# Each pattern: (regex, risk_level, reason, safe_alternative)
DANGEROUS_PATTERNS = [
    (
        re.compile(
            r'\brm\s+(?:-[rR][fF]|-[fF][rR]|-[rR][fF][rR]?)\b'
            r'|\brm\s+-[rR]f?\s+\S*[/\\*]'
            r'|\brm\s+-[rR]f?\s+(?:--no-preserve-root|/|\*)'
        ),
        "dangerous",
        "Recursive force remove — permanently deletes files without confirmation. "
        "Can destroy entire filesystems if run on / or /*.",
        "Use 'trash' (trash-cli) or a recycle-bin aware tool instead of rm -rf. "
        "For safe cleanup: 'rm -ri' (interactive) or 'rm -d' (empty dirs only).",
    ),
    (
        re.compile(
            r'\b(?:del|erase)\s*/[sSqQfF]|\bdel/[sSqQfF]',
        ),
        "dangerous",
        "Recursive Windows delete — permanently removes files matching the pattern "
        "from all subdirectories without recovery.",
        "Use 'del' without /S for current directory only, or move files to a "
        "recycle-bin location first.",
    ),
    (
        re.compile(
            r'\b(?:rmdir|rd)\s+/[sSqQ]?\s',
        ),
        "dangerous",
        "Recursive directory removal — deletes a directory tree permanently on Windows.",
        "Use 'rmdir' without /S for empty directories, or review contents before deletion.",
    ),
    (
        re.compile(
            r'\bformat\s+\S',
        ),
        "dangerous",
        "Disk format command — erases all data on a drive partition.",
        "Use 'diskutil info' or 'lsblk' to inspect drives first. Only format explicitly "
        "identified volumes after verification.",
    ),
    (
        re.compile(
            r'\bmkfs\.\w+\s',
        ),
        "dangerous",
        "Filesystem creation tool — overwrites existing data on a partition to "
        "create a new filesystem.",
        "Verify the target device with 'lsblk' or 'diskutil list' before running mkfs. "
        "Ensure you're not overwriting an active data partition.",
    ),
    (
        re.compile(
            r'\bdd\s+if=.*\s+of=',
        ),
        "dangerous",
        "dd (disk destroyer) — can overwrite arbitrary disk blocks or devices. "
        "A small typo in 'of=' can brick a system or wipe data.",
        "Use 'cp' for file copies, 'rsync' for syncs. For disk images, double-check "
        "the 'of=' target three times.",
    ),
    (
        re.compile(
            r'(?:curl|wget)\s+.*?\s*\|\s*(?:sh|bash|zsh|dash|ksh)\b',
        ),
        "dangerous",
        "Shell pipe from network — downloads and immediately executes a remote script. "
        "This is a classic supply-chain attack vector. The script can contain anything.",
        "Download the script first, inspect it manually: 'curl -L <url> -o script.sh', "
        "then review before running. Better yet, use your package manager.",
    ),
    (
        re.compile(
            r'(?:Invoke-WebRequest|iwr|wget|curl)\s+.*?(?:-UseBasicParsing)?.*?\s*[|]\s*'
            r'(?:Invoke-Expression|iex|IEX)\b',
        ),
        "dangerous",
        "PowerShell download-and-execute — downloads a remote payload and executes "
        "it in memory. Common malware initial-access pattern.",
        "Use Install-Script or Install-Module from trusted PSGallery. For manual "
        "scripts, download to disk, inspect, then run explicitly.",
    ),
    (
        re.compile(
            r'Start-Process\s+.*?-FilePath\s+.*?(?:net\.http|webclient|download)',
        ),
        "dangerous",
        "PowerShell process launch from downloaded content — executes a binary "
        "or script retrieved from a remote source.",
        "Use trusted package managers (winget, choco, scoop) to install software. "
        "Verify publisher signatures for downloaded executables.",
    ),
    (
        re.compile(
            r'(?:chmod|chown)\s+-[Rr]\s+'
            r'(?:\d{3,4}|[a-zA-Z][a-zA-Z0-9._-]*:[a-zA-Z][a-zA-Z0-9._-]*)\s+/|'
            r'chmod\s+777\s|'
            r'chmod\s+-[Rr]\s+777\s|'
            r'chown\s+-[Rr]\s+.*?/\s',
        ),
        "dangerous",
        "Dangerous permission change — recursive chmod 777 or chown -R on a "
        "system path grants wide-open access or changes ownership broadly.",
        "Use targeted permissions: 'chmod 755' for dirs, 'chmod 644' for files. "
        "Avoid recursive chown unless absolutely necessary and specific.",
    ),
    (
        re.compile(
            r'\bgit\s+clean\s+-[fF][dDxX]',
        ),
        "dangerous",
        "Destructive git clean — removes untracked files AND directories from "
        "the working tree. With -x also removes gitignored files. Data loss risk.",
        "Use 'git clean -n' to preview first. Use 'git clean -f' (no -d) for files only. "
        "Commit or stash untracked content you might need.",
    ),
    (
        re.compile(
            r'\bgit\s+reset\s+--hard\s+(?:HEAD|origin)',
        ),
        "warning",
        "Hard git reset — discards all local changes in the working directory "
        "and staging area. Uncommitted work is lost.",
        "Use 'git stash' to save changes before resetting. Use 'git reset --soft' "
        "to keep changes staged.",
    ),
    (
        re.compile(
            r'\bgit\s+push\s+.*?--force\b(?!-with-lease)',
        ),
        "warning",
        "Force git push — overwrites remote history. Can destroy collaborators' work "
        "and cause repository corruption if not coordinated.",
        "Use 'git push --force-with-lease' which checks if your remote branch has "
        "advanced before force-pushing.",
    ),
    (
        re.compile(
            r'\bnpm\s+(?:install|ci)\s+.*?(?:--unsafe-perm|--allow-root|--ignore-scripts)',
        ),
        "warning",
        "Dangerous npm flags — --unsafe-perm runs install scripts as root, "
        "--ignore-scripts bypasses package security checks.",
        "Avoid --unsafe-perm unless you understand the consequences. Use 'npm install' "
        "without special flags for normal operations.",
    ),
    (
        re.compile(
            r'(?:pip|pip3)\s+install\s+.*?(?:https?://|git\+)',
        ),
        "warning",
        "pip install from URL — installs a package from an arbitrary URL instead of "
        "PyPI. Could contain malicious code if the URL is untrusted.",
        "Use 'pip install <package_name>' to install from PyPI. For development, "
        "add the private repo to requirements.txt with a hash check.",
    ),
    (
        re.compile(
            r'(?:pip|pip3)\s+install\s+-r\s+.*?[^/\\]'
        ),
        "safe",
        "Pip install from requirements file — generally safe, but review the "
        "requirements file first for pinned versions and trusted sources.",
        "Pin all versions in requirements.txt and use 'pip install --require-hashes' "
        "for production environments.",
    ),
]

WARNING_PATTERNS = [
    (
        re.compile(
            r'(?:sudo|doas)\s+(?:rm|del|format|mkfs|dd|shutdown|reboot|poweroff)\b',
        ),
        "warning",
        "Privileged destructive command — running a destructive command with "
        "elevated privileges. A typo can cause system-wide damage.",
        "Always use the minimum privilege needed. Double-check the command before "
        "pressing Enter when using sudo on destructive operations.",
    ),
    (
        re.compile(
            r'(?:>|>>)\s*(?:/dev/sda|/dev/sdb|/dev/nvme|/dev/mmcblk|/dev/disk)',
        ),
        "dangerous",
        "Output redirection to a block device — writing output directly to a "
        "raw disk device, which overwrites partition tables and data.",
        "Redirect to a regular file (e.g., '> backup.img') instead of a device node.",
    ),
    (
        re.compile(
            r'(?::\s*)?\{\s*,\s*\}\s*(?:;|&&|\|\|)',
        ),
        "warning",
        "Brace expansion bomb — a single command can expand into thousands or "
        "millions of operations, causing system strain or DoS.",
        "Test brace expansion with 'echo' first. Use 'seq' or loops with "
        "limits for large iteration counts.",
    ),
    (
        re.compile(
            r'\b(?:shutdown|reboot|poweroff|halt|init\s+0|init\s+6)\b',
        ),
        "warning",
        "System shutdown/reboot command — will terminate running processes "
        "and shut down or restart the system.",
        "Use 'shutdown -c' to cancel a pending shutdown. Add a delay: "
        "'shutdown -h +5' (5 minute delay). Notify other users first.",
    ),
    (
        re.compile(
            r'(?:eval|exec)\s+\$?\(',
        ),
        "dangerous",
        "Dynamic command evaluation — eval/exec with command substitution can "
        "execute arbitrary commands from variables, enabling injection attacks.",
        "Avoid eval entirely. Use arrays and proper quoting instead of "
        "command substitution in strings.",
    ),
    (
        re.compile(
            r'>\s*/dev/null\s+2>&1\s+&&\s+curl',
        ),
        "warning",
        "Silent remote execution — suppresses all output/errors then runs a "
        "network command. Common in obfuscated one-liner attacks.",
        "Keep output visible when running network commands. Use verbose "
        "flags (-v) to see what's happening.",
    ),
]

SAFE_PATTERNS = [
    (
        re.compile(r'\bls\b'),
        "safe",
        "List directory contents — no destructive potential.",
        "",
    ),
    (
        re.compile(r'\b(?:cd|pwd)\b'),
        "safe",
        "Navigation commands — change directory or print working directory.",
        "",
    ),
    (
        re.compile(r'\bgrep\b'),
        "safe",
        "Text search — searches file contents without modifying anything.",
        "",
    ),
    (
        re.compile(r'\bcp\b'),
        "safe",
        "File copy — duplicates files. Generally safe with normal usage.",
        "",
    ),
    (
        re.compile(r'\bmv\b'),
        "safe",
        "Move/rename files. Can be destructive if overwriting existing files.",
        "Use 'mv -i' (interactive) to be prompted before overwriting.",
    ),
    (
        re.compile(r'\bcat\b'),
        "safe",
        "Concatenate/display file contents — read-only operation.",
        "",
    ),
    (
        re.compile(r'\b(?:python|python3)\s+\S+\.py\b'),
        "safe",
        "Run a Python script — generally safe if the script is trusted.",
        "Review scripts from untrusted sources before running.",
    ),
    (
        re.compile(r'\bgit\s+(?:status|log|diff|branch|add|commit|checkout)\b'),
        "safe",
        "Git operations — standard version control commands.",
        "",
    ),
]

# Direct string-based detection (used when regex isn't ideal)
DANGEROUS_CMDS = [
    "rm -rf",
    "rm -fr",
    "rm -rf /",
    "rm -rf /*",
    "del /s",
    "del /f",
    "del /q",
    "format",
    "format c:",
    "mkfs",
    "dd if=",
    "curl bash",
    "curl sh",
    "wget -O - | sh",
    "iex",
    "Invoke-Expression",
    "chmod -R 777",
    "chown -R",
    "git clean -fdx",
    "git clean -fd",
    "git clean -fx",
]

EXCLUDE_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".tox", ".eggs", "build", "dist", ".next", "vendor",
    "target", ".svn", ".hg", ".idea", ".vscode",
    "bower_components", "jspm_packages", ".cache",
})

# ---------------------------------------------------------------------------
# Detection logic
# ---------------------------------------------------------------------------


def classify_command(command: str) -> dict:
    """Classify a single command string by safety level."""
    cmd_lower = command.lower().strip()

    # Ignore empty / trivial commands
    if not cmd_lower or cmd_lower in ("", " ", "\n"):
        return {
            "command": command,
            "classification": "safe",
            "reason": "Empty or trivial command — no action taken.",
            "safe_alternative": "",
            "matched_pattern": None,
        }

    result = {
        "command": command,
        "classification": "safe",
        "reason": "",
        "safe_alternative": "",
        "matched_pattern": None,
    }

    highest_risk = "safe"

    # Check dangerous patterns first
    for pattern_obj, risk_level, reason, alternative in DANGEROUS_PATTERNS:
        match = pattern_obj.search(command)
        if match:
            risk = risk_level
            if _risk_score(risk) > _risk_score(highest_risk):
                highest_risk = risk
                result["classification"] = risk
                result["reason"] = reason
                result["safe_alternative"] = alternative
                result["matched_pattern"] = match.group()

    # Check warning patterns (if not already dangerous)
    for pattern_obj, risk_level, reason, alternative in WARNING_PATTERNS:
        if highest_risk == "dangerous":
            break
        match = pattern_obj.search(command)
        if match:
            if _risk_score(risk_level) > _risk_score(highest_risk):
                highest_risk = risk_level
                result["classification"] = risk_level
                result["reason"] = reason
                result["safe_alternative"] = alternative
                result["matched_pattern"] = match.group()

    # Check safe patterns (if classification is still "safe")
    if highest_risk == "safe":
        for pattern_obj, risk_level, reason, alternative in SAFE_PATTERNS:
            match = pattern_obj.search(command)
            if match:
                result["classification"] = "safe"
                result["reason"] = reason
                result["safe_alternative"] = alternative
                result["matched_pattern"] = match.group()
                break

    # Additional chain detection for piped dangerous combos
    pipe_danger = _detect_pipe_danger(command)
    if pipe_danger and _risk_score(pipe_danger["risk"]) > _risk_score(highest_risk):
        highest_risk = pipe_danger["risk"]
        result["classification"] = pipe_danger["risk"]
        result["reason"] = pipe_danger["reason"]
        result["safe_alternative"] = pipe_danger.get("safe_alternative", "")
        result["matched_pattern"] = pipe_danger.get("match", "")

    return result


def _risk_score(level: str) -> int:
    """Convert risk level string to numeric score for comparison."""
    return {"safe": 0, "warning": 1, "dangerous": 2}.get(level, 0)


def _detect_pipe_danger(command: str) -> dict | None:
    """Detect dangerous pipe chains not caught by individual regex."""
    cmd_lower = command.lower().strip()

    # sudo curl ... | sh (or similar sudo-pipe combos)
    if (
        re.search(r'sudo\s+(?:curl|wget)\b', cmd_lower)
        and re.search(r'\|\s*(?:sh|bash)\b', cmd_lower)
    ):
        return {
            "risk": "dangerous",
            "reason": "Sudo download-and-pipe-to-shell — downloads a script with "
            "root privileges and executes it without inspection. Extreme risk.",
            "safe_alternative": "Download separately, inspect, then run with "
            "minimum privileges needed.",
            "match": "sudo <download> | sh",
        }

    # Multiple pipes with dangerous chaining
    if re.search(r'\b(?:curl|wget)\b.*?\|.*?\|', cmd_lower):
        return {
            "risk": "warning",
            "reason": "Multi-stage pipeline with network download — command contains "
            "a network fetch piped through multiple stages, making it harder to "
            "audit what's actually being executed.",
            "safe_alternative": "Break the pipeline into separate steps and "
            "inspect intermediate output.",
            "match": "curl|...|...",
        }

    return None


def batch_classify(commands: list[str]) -> list[dict]:
    """Classify multiple commands and return results."""
    return [classify_command(cmd) for cmd in commands]


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

RISK_ICONS = {
    "safe": "\U0001f7e2",       # 🟢 green circle
    "warning": "\U0001f7e1",    # 🟡 yellow circle
    "dangerous": "\U0001f534",  # 🔴 red circle
}

RISK_LABELS = {
    "safe": "SAFE",
    "warning": "WARNING",
    "dangerous": "DANGEROUS",
}

EXIT_CODES = {
    "safe": 0,
    "warning": 1,
    "dangerous": 2,
}


def print_report(result: dict, explain: bool = False) -> None:
    """Print a formatted safety report for a single command."""
    cls = result["classification"]
    icon = RISK_ICONS.get(cls, "\u2753")
    label = RISK_LABELS.get(cls, cls.upper())

    print(f"\n{icon}  COMMAND GUARD — {label}")
    print(f"{'=' * 60}")
    print(f"  Command:    {result['command']}")
    print(f"  Verdict:    {icon} {label}")

    if result.get("matched_pattern"):
        print(f"  Trigger:    {result['matched_pattern']}")

    if result.get("reason"):
        print(f"\n  \U0001f4a1 Reason:")
        print(f"    {result['reason']}")

    if result.get("safe_alternative"):
        print(f"\n  \U0001f504 Safe Alternative:")
        print(f"    {result['safe_alternative']}")

    if explain and cls == "safe":
        print(f"\n  \u2705 This command appears safe to run.")
    elif explain and cls in ("warning", "dangerous"):
        print(f"\n  \u26a0\ufe0f Proceed with extreme caution or cancel this operation.")
    print()


def print_json_report(result: dict) -> None:
    """Output classification result as JSON."""
    print(json.dumps(result, indent=2, ensure_ascii=False))


def print_batch_report(results: list[dict]) -> None:
    """Print formatted report for multiple commands."""
    dangerous = [r for r in results if r["classification"] == "dangerous"]
    warnings = [r for r in results if r["classification"] == "warning"]
    safe = [r for r in results if r["classification"] == "safe"]

    total = len(results)
    print(f"\n\U0001f50d COMMAND GUARD — Batch Scan: {total} command(s)")
    print(f"{'=' * 60}")
    print(f"  {RISK_ICONS['dangerous']} DANGEROUS: {len(dangerous)}")
    print(f"  {RISK_ICONS['warning']} WARNING:   {len(warnings)}")
    print(f"  {RISK_ICONS['safe']} SAFE:      {len(safe)}")
    print()

    for r in dangerous:
        icon = RISK_ICONS["dangerous"]
        print(f"  {icon} [{RISK_LABELS['dangerous']}] {r['command']}")
        if r.get("reason"):
            print(f"     {r['reason'][:120]}...")
        print()

    for r in warnings:
        icon = RISK_ICONS["warning"]
        print(f"  {icon} [{RISK_LABELS['warning']}] {r['command']}")
        if r.get("reason"):
            print(f"     {r['reason'][:120]}...")
        print()

    for r in safe:
        icon = RISK_ICONS["safe"]
        print(f"  {icon} [{RISK_LABELS['safe']}] {r['command']}")
        print()


def print_known_dangerous() -> None:
    """Print a quick reference of detected dangerous commands."""
    print(f"\n{'=' * 60}")
    print("  \U0001f6ab COMMAND GUARD — Known Dangerous Patterns")
    print(f"{'=' * 60}")
    print("  The following categories of commands are detected:\n")
    print(f"  {RISK_ICONS['dangerous']} Recursive deletes:   rm -rf, del /s, rmdir /s, rd /s")
    print(f"  {RISK_ICONS['dangerous']} Disk destruction:     format, mkfs.*, dd if=... of=")
    print(f"  {RISK_ICONS['dangerous']} Pipe-to-shell:        curl|sh, wget|sh, iwr|iex")
    print(f"  {RISK_ICONS['dangerous']} Permission bombs:     chmod 777, chmod -R 777, chown -R /")
    print(f"  {RISK_ICONS['dangerous']} Destructive git:      git clean -fdx, git reset --hard")
    print(f"  {RISK_ICONS['dangerous']} Block device writes:  > /dev/sda, > /dev/nvme")
    print(f"  {RISK_ICONS['dangerous']} Dynamic eval:         eval $(...), exec $(...)")
    print(f"  {RISK_ICONS['warning']} Force push:           git push --force")
    print(f"  {RISK_ICONS['warning']} Unsafe npm flags:     npm install --unsafe-perm")
    print(f"  {RISK_ICONS['warning']} URL pip install:      pip install <url>")
    print(f"  {RISK_ICONS['warning']} System commands:      shutdown, reboot, poweroff")
    print(f"  {RISK_ICONS['warning']} Sudo destructions:    sudo rm, sudo dd, sudo format")
    print()


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="command_guard.py — Check terminal commands for safety before execution.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python command_guard.py "rm -rf /"
  python command_guard.py "ls -la" --json
  python command_guard.py "curl https://x.sh | sh" --explain
  python command_guard.py --batch "cmd1" "cmd2" "cmd3"
  python command_guard.py --list-patterns
  echo "some command" | python command_guard.py --stdin
        """,
    )
    parser.add_argument("commands", nargs="*", help="Command(s) to check")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--explain", "-e", action="store_true",
                        help="Show extended explanation even for safe commands")
    parser.add_argument("--batch", "-b", nargs="+", metavar="CMD",
                        help="Check multiple commands in batch mode")
    parser.add_argument("--stdin", "-i", action="store_true",
                        help="Read commands from stdin (one per line)")
    parser.add_argument("--list-patterns", "-l", action="store_true",
                        help="List all known dangerous/warning patterns")
    parser.add_argument("--version", "-V", action="version",
                        version="command_guard.py v1.0.0")

    args = parser.parse_args()

    # --list-patterns flag
    if args.list_patterns:
        print_known_dangerous()
        sys.exit(0)

    # Collect commands to check
    cmds_to_check: list[str] = []

    if args.batch:
        cmds_to_check = list(args.batch)
    elif args.stdin:
        cmd_input = sys.stdin.read()
        cmds_to_check = [
            line.strip() for line in cmd_input.splitlines()
            if line.strip()
        ]
    elif args.commands:
        cmds_to_check = list(args.commands)
    else:
        parser.print_help()
        print(
            "\n  \u274c Please provide a command to check, "
            "or use --stdin / --batch.",
            file=sys.stderr
        )
        sys.exit(1)

    # Classify
    if len(cmds_to_check) == 1:
        result = classify_command(cmds_to_check[0])
        if args.json:
            print_json_report(result)
        else:
            print_report(result, explain=args.explain)
        sys.exit(EXIT_CODES.get(result["classification"], 0))
    else:
        results = batch_classify(cmds_to_check)
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            print_batch_report(results)

        # Determine overall exit code (highest risk wins)
        overall = max(
            (r["classification"] for r in results),
            key=lambda x: _risk_score(x),
        )
        sys.exit(EXIT_CODES.get(overall, 0))


if __name__ == "__main__":
    main()
