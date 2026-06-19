#!/usr/bin/env python3
"""
security_scan.py — Scan project files for hardcoded secrets & security risks.

Detects:
  - Hardcoded API keys, tokens, passwords, secrets
  - Private/secret key files (.pem, .key, .env with secrets)
  - Insecure patterns (eval, exec, dangerous imports)
  - Exposed internal IPs / hostnames in code
  - Commented-out authentication or credentials

Gebruik:
    python security_scan.py <path>
    python security_scan.py <path> --json
    python security_scan.py <path> --patterns-only
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
# Risk patterns per file type
# ---------------------------------------------------------------------------

HIGH_RISK_PATTERNS = {
    "api_key": re.compile(
        r'(?i)(?:api[_-]?key|apikey|api[_-]?secret|api_secret)\s*[=:]\s*["\']([^"\'\s]{8,})["\']'
    ),
    "password": re.compile(
        r'(?i)(?:password|pwd|passwd|secret)\s*[=:]\s*["\']([^"\'\s]{4,})["\']'
    ),
    "token": re.compile(
        r'(?i)(?:token|bearer|jwt|auth_token|access_token|'
        r'refresh_token)\s*[=:]\s*["\']([^"\'\\s]{8,})["\']'
    ),
    "aws_key": re.compile(
        r'(?i)AKIA[0-9A-Z]{16}'
    ),
    "private_key": re.compile(
        r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'
    ),
    "connection_string": re.compile(
        r'(?i)(?:mongodb|postgresql|mysql|redis|amqp|rabbitmq)://[^"\'\s]+:[^"\'\s]+@'
    ),
}

MEDIUM_RISK_PATTERNS = {
    "eval_exec": re.compile(
        r'\b(?:eval|exec|execfile|__import__)\s*\('
    ),
    "pickle_usage": re.compile(
        r'\b(?:pickle\.loads?|cPickle\.loads?|dill\.loads?|cloudpickle\.loads?)\s*\('
    ),
    "shell_injection": re.compile(
        r'(?:os\.system|subprocess\.[a-z_]+\s*\([^)]*\bshell\s*=\s*True)'
    ),
    "sql_injection": re.compile(
        r'(?i)(?:execute|executemany|rawsql|query)\s*\(\s*f["\']'
    ),
    "yaml_load": re.compile(
        r'(?i)(?:yaml\.load|yaml_load)\s*\('
    ),
    "assert_used": re.compile(
        r'^\s*assert\s+',
        re.MULTILINE
    ),
}

LOW_RISK_PATTERNS = {
    "hardcoded_ip": re.compile(
        r'(?<!\d)(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|'
        r'172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|'
        r'192\.168\.\d{1,3}\.\d{1,3})(?!\d)'
    ),
    "localhost_url": re.compile(
        r'(?:http://localhost|http://127\.0\.0\.1)(?::\d+)?'
    ),
    "commented_auth": re.compile(
        r'^\s*#.*(?:password|api_key|secret|token)\s*[=:]',
        re.MULTILINE | re.IGNORECASE
    ),
    "env_with_secret": re.compile(
        r'(?i)^\s*(?:export\s+)?(?:SECRET|API_KEY|TOKEN|PASSWORD|DB_PASS|AUTH_KEY)\s*=\s*\S',
        re.MULTILINE
    ),
}

# ---------------------------------------------------------------------------
# Fix suggestions per pattern key
# ---------------------------------------------------------------------------

FIX_SUGGESTIONS = {
    "api_key": "Use environment variables (os.getenv) or a secrets manager instead of hardcoding.",
    "password": "Never hardcode passwords. Store in .env or a secrets vault.",
    "token": "Use environment variables or short-lived tokens from a provider.",
    "aws_key": "AWS IAM user keys should not be in source code. Use IAM roles or env vars.",
    "private_key": "Private keys should never be committed. Use SSH agent or secrets manager.",
    "connection_string": (
        "Move connection strings to environment variables"
        " or a config file outside the repo."),
    "eval_exec": "Avoid eval/exec — it allows arbitrary code execution. Use safer alternatives.",
    "pickle_usage": (
        "Pickle is insecure for untrusted data."
        " Consider JSON or structured serialization."),
    "shell_injection": "Avoid shell=True in subprocess calls. Use argument lists instead.",
    "sql_injection": "Use parameterized queries (?, %s) instead of f-string interpolation.",
    "yaml_load": "Use yaml.safe_load() instead of unsafe YAML loading.",
    "assert_used": "assert statements are stripped with -O. Use proper error handling instead.",
    "hardcoded_ip": "Hardcoded IPs make deployment inflexible. Use config or env vars.",
    "localhost_url": "Hardcoded localhost URLs break in production. Use relative URLs or config.",
    "commented_auth": "Remove commented-out credentials entirely — they leak intent.",
    "env_with_secret": "Secrets in .env files should be gitignored and never committed.",
}

RISK_LEVELS = {
    "api_key": "HIGH",
    "password": "HIGH",
    "token": "HIGH",
    "aws_key": "HIGH",
    "private_key": "HIGH",
    "connection_string": "HIGH",
    "eval_exec": "MEDIUM",
    "pickle_usage": "MEDIUM",
    "shell_injection": "MEDIUM",
    "sql_injection": "MEDIUM",
    "yaml_load": "MEDIUM",
    "assert_used": "LOW",
    "hardcoded_ip": "LOW",
    "localhost_url": "LOW",
    "commented_auth": "MEDIUM",
    "env_with_secret": "HIGH",
}

EXCLUDE_DIRS = frozenset({
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    ".tox", ".eggs", "build", "dist", ".next", "vendor",
    ".backups", ".self_improve_reports", "release",
})

EXCLUDE_EXTENSIONS = frozenset({
    ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".mp4", ".ogg", ".wav",
    ".zip", ".tar", ".gz", ".bz2", ".7z",
    ".lock", ".sum",
})


def scan_file(filepath: Path) -> list[dict]:
    """Scan a single file for security issues."""
    ext = filepath.suffix.lower()
    if ext in EXCLUDE_EXTENSIONS:
        return []

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    lines = content.split("\n")
    findings = []

    # Check each pattern
    for pattern_name, pattern in HIGH_RISK_PATTERNS.items():
        for match in pattern.finditer(content):
            line_no = content[:match.start()].count("\n") + 1
            context_line = lines[line_no - 1].strip() if line_no <= len(lines) else ""
            findings.append({
                "file": str(filepath),
                "line": line_no,
                "risk": "HIGH",
                "pattern": pattern_name,
                "match": _mask_secret(match.group())[:100],
                "context": context_line[:120],
                "fix": FIX_SUGGESTIONS.get(pattern_name, ""),
            })

    for pattern_name, pattern in MEDIUM_RISK_PATTERNS.items():
        for match in pattern.finditer(content):
            line_no = content[:match.start()].count("\n") + 1
            context_line = lines[line_no - 1].strip() if line_no <= len(lines) else ""
            findings.append({
                "file": str(filepath),
                "line": line_no,
                "risk": "MEDIUM",
                "pattern": pattern_name,
                "match": match.group()[:100],
                "context": context_line[:120],
                "fix": FIX_SUGGESTIONS.get(pattern_name, ""),
            })

    for pattern_name, pattern in LOW_RISK_PATTERNS.items():
        for match in pattern.finditer(content):
            line_no = content[:match.start()].count("\n") + 1
            context_line = lines[line_no - 1].strip() if line_no <= len(lines) else ""
            findings.append({
                "file": str(filepath),
                "line": line_no,
                "risk": "LOW",
                "pattern": pattern_name,
                "match": match.group()[:100],
                "context": context_line[:120],
                "fix": FIX_SUGGESTIONS.get(pattern_name, ""),
            })

    return findings


def _mask_secret(text: str) -> str:
    """Mask the value part of a secret-like match."""
    for sep in ['="', "='", "= ", ": ", ":\"", ":'"]:
        if sep in text:
            parts = text.split(sep, 1)
            if len(parts) == 2 and len(parts[1]) > 4:
                val = parts[1]
                return parts[0] + sep + val[:2] + "****" + val[-1:]
    return text[:20] + "****"


def collect_files(root: Path) -> list[Path]:
    """Collect all text source files in the given path."""
    files = []

    if root.is_file():
        return [root]

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded dirs
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            fp = Path(dirpath) / fn
            ext = fp.suffix.lower()
            if ext not in EXCLUDE_EXTENSIONS:
                files.append(fp)

    return sorted(files)


def print_report(findings: list[dict], patterns_only: bool = False) -> None:
    """Print a formatted report of all findings."""
    if not findings:
        print("\n ✅ Geen security issues gevonden!")
        return

    high = [f for f in findings if f["risk"] == "HIGH"]
    medium = [f for f in findings if f["risk"] == "MEDIUM"]
    low = [f for f in findings if f["risk"] == "LOW"]

    print(f"\n{'='*60}")
    print(f" 🔒 SECURITY SCAN — {len(findings)} finding(s)")
    print(f"{'='*60}")
    print(f"   🔴 HIGH:   {len(high)}")
    print(f"   🟡 MEDIUM: {len(medium)}")
    print(f"   🟢 LOW:    {len(low)}")
    print()

    if patterns_only:
        # Group by pattern
        by_pattern = {}
        for f in findings:
            by_pattern.setdefault(f["pattern"], []).append(f)

        for pattern_name, items in sorted(by_pattern.items()):
            risk = items[0]["risk"]
            risk_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}[risk]
            print(f"\n {risk_icon} [{risk}] {pattern_name} ({len(items)}x)")
            print(f"   💡 {FIX_SUGGESTIONS.get(pattern_name, '')}")
            for item in items[:5]:
                print(f"   📄 {item['file']}:{item['line']}  →  {item['context']}")
            if len(items) > 5:
                print(f"   ... en nog {len(items) - 5} meer")
        return

    for item in findings:
        risk_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}[item["risk"]]
        print(f" {risk_icon} [{item['risk']}] {item['file']}:{item['line']}")
        print(f"   Pattern: {item['pattern']}")
        print(f"   Match:   {item['match']}")
        print(f"   Context: {item['context']}")
        if item["fix"]:
            print(f"   💡 {item['fix']}")
        print()


def print_json(findings: list[dict]) -> None:
    """Output findings as JSON."""
    output = {
        "total": len(findings),
        "by_risk": {
            "high": len([f for f in findings if f["risk"] == "HIGH"]),
            "medium": len([f for f in findings if f["risk"] == "MEDIUM"]),
            "low": len([f for f in findings if f["risk"] == "LOW"]),
        },
        "findings": findings,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="security_scan.py — Scan project for hardcoded secrets & security risks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python security_scan.py src/
  python security_scan.py script.py
  python security_scan.py . --json
  python security_scan.py . --patterns-only
        """,
    )
    parser.add_argument("path", help="Bestand of directory om te scannen")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--patterns-only", "-p", action="store_true",
                        help="Groepeer resultaten per patroon i.p.v. per file")
    parser.add_argument("--version", action="version", version="security_scan.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    files = collect_files(target)
    if not files:
        print(" Geen bestanden om te scannen")
        sys.exit(0)

    print(f"\n🔍 Security Scan v1.0.0 — scanning {len(files)} bestand(en) in {target}")

    all_findings = []
    for fp in files:
        findings = scan_file(fp)
        all_findings.extend(findings)

    if args.json:
        print_json(all_findings)
    else:
        print_report(all_findings, args.patterns_only)


if __name__ == "__main__":
    main()
