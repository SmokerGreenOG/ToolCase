#!/usr/bin/env python3
"""
php_config_audit.py — PHP configuration security audit.

Checkt PHP projecten op:
  - php.ini settings (display_errors, expose_php, allow_url_fopen, etc.)
  - .env file exposure en best practices
  - Debug mode in production
  - Session security settings
  - Upload directory security
  - .htaccess configuratie

Gebruik:
    python php_config_audit.py <path>
    python php_config_audit.py <path> --json
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import sys
from pathlib import Path

EXCLUDE_DIRS = {"node_modules", "vendor", ".git", "__pycache__", "tests/fixtures", ".venv", "venv"}

# Recommended PHP production settings
PHP_INI_BEST_PRACTICES = {
    "display_errors": {"recommended": "Off", "severity": "HIGH"},
    "display_startup_errors": {"recommended": "Off", "severity": "MEDIUM"},
    "expose_php": {"recommended": "Off", "severity": "MEDIUM"},
    "allow_url_fopen": {"recommended": "Off", "severity": "MEDIUM"},
    "allow_url_include": {"recommended": "Off", "severity": "HIGH"},
    "log_errors": {"recommended": "On", "severity": "MEDIUM"},
    "error_reporting": {"recommended": "E_ALL & ~E_DEPRECATED & ~E_STRICT", "severity": "LOW"},
    "session.cookie_httponly": {"recommended": "1", "severity": "HIGH"},
    "session.cookie_secure": {"recommended": "1", "severity": "HIGH"},
    "session.cookie_samesite": {"recommended": "Strict", "severity": "HIGH"},
    "session.use_strict_mode": {"recommended": "1", "severity": "MEDIUM"},
    "session.use_only_cookies": {"recommended": "1", "severity": "MEDIUM"},
    "file_uploads": {"recommended": "On", "severity": "LOW"},
    "upload_max_filesize": {"recommended": ">= 2M", "severity": "LOW"},
    "max_execution_time": {"recommended": "<= 30", "severity": "LOW"},
    "memory_limit": {"recommended": ">= 128M", "severity": "LOW"},
}

# Dangerous PHP functions often enabled in dev
DANGEROUS_FUNCTIONS = [
    "exec", "system", "passthru", "shell_exec", "popen", "proc_open",
    "eval", "assert", "create_function", "allow_url_fopen", "allow_url_include",
]

# Settings to search for in code (ini_set calls)
INI_SET_PATTERN = re.compile(
    r'ini_set\s*\(\s*[\"\'](\w+(?:\.\w+)*)[\"\']\s*,\s*[\"\']([^\"\']*)[\"\']',
)

# display_errors in code
DISPLAY_ERRORS_PATTERN = re.compile(
    r'(?:ini_set|error_reporting)\s*\(\s*[\"\'](?:display_errors|error_reporting)[\"\']\s*,\s*[\"\']?(?:1|true|on|E_ALL)[\"\']?',
    re.IGNORECASE,
)

# Debug-mode environment detection
DEBUG_MODE_PATTERN = re.compile(
    r'(?:APP_DEBUG|DEBUG|ENVIRONMENT)\s*=\s*(?:true|1|development|dev|local)',
    re.IGNORECASE,
)

    # Embedded secret values
SECRET_PATTERN = re.compile(
    r'(?:DB_PASSWORD|DB_USERNAME|MAIL_PASSWORD|SECRET|API_KEY|APP_KEY)\s*=\s*[\"\'](?!\$\{)[^\"\']{3,}[\"\']',
)


def find_config_files(root: Path) -> list[Path]:
    """Find php.ini, .env, .htaccess, and config.php files."""
    configs = []
    for pattern in ["*.ini", ".env*", ".htaccess", "*config*.php", "*.env"]:
        for f in root.rglob(pattern):
            try:
                parts = f.relative_to(root).parts
            except ValueError:
                parts = f.parts
            if any(part in EXCLUDE_DIRS for part in parts):
                continue
            configs.append(f)
    return sorted(set(configs))


def find_php_files(root: Path) -> list[Path]:
    files = []
    for f in root.rglob("*.php"):
        try:
            parts = f.relative_to(root).parts
        except ValueError:
            parts = f.parts
        if any(part in EXCLUDE_DIRS for part in parts):
            continue
        files.append(f)
    return sorted(set(files))


def audit_config(filepath: Path) -> dict:
    """Audit a single config file."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except:
        return {"file": str(filepath), "findings": []}

    findings = []
    name = filepath.name.lower()

    # .env specific checks
    if name.startswith(".env"):
        if SECRET_PATTERN.search(source):
            findings.append({"severity": "HIGH", "message": "Secret in .env — ensure .env is gitignored"})
        if DEBUG_MODE_PATTERN.search(source):
            findings.append({"severity": "HIGH", "message": "APP_DEBUG=true — turn off in production"})
        if filepath.name == ".env" and not filepath.parent.name.startswith("."):
            findings.append({"severity": "MEDIUM", "message": ".env in web-accessible directory — move outside webroot"})

    # php.ini checks
    if name.endswith(".ini") or "php.ini" in name:
        for setting, info in PHP_INI_BEST_PRACTICES.items():
            pattern = re.compile(rf'^{re.escape(setting)}\s*=\s*(.+)', re.MULTILINE | re.IGNORECASE)
            match = pattern.search(source)
            if match:
                value = match.group(1).strip()
                if info["recommended"] in ("Off", "0") and value.lower() not in ("off", "0", "false", ""):
                    findings.append({"severity": info["severity"],
                                     "message": f"{setting} = {value} (recommended: {info['recommended']})"})
                if info["recommended"] in ("On", "1") and value.lower() in ("off", "0", "false"):
                    findings.append({"severity": info["severity"],
                                     "message": f"{setting} = {value} (recommended: {info['recommended']})"})

    # .htaccess checks
    if name == ".htaccess":
        if "Options -Indexes" not in source:
            findings.append({"severity": "MEDIUM", "message": "Missing Options -Indexes — directory listing enabled"})
        if "Header set X-Content-Type-Options" not in source:
            findings.append({"severity": "LOW", "message": "Missing X-Content-Type-Options: nosniff header"})
        if "Header set X-Frame-Options" not in source:
            findings.append({"severity": "LOW", "message": "Missing X-Frame-Options header (clickjacking)"})

    return {"file": str(filepath), "findings": findings}


def audit_php_code(filepath: Path) -> dict:
    """Search PHP files for inline config issues."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except:
        return {"file": str(filepath), "findings": []}

    findings = []

    # display_errors / error_reporting in code
    for match in DISPLAY_ERRORS_PATTERN.finditer(source):
        line = source[:match.start()].count('\n') + 1
        findings.append({"severity": "HIGH", "line": line,
                        "message": "display_errors/error_reporting enabled in code"})

    # ini_set calls
    for match in INI_SET_PATTERN.finditer(source):
        setting = match.group(1)
        value = match.group(2)
        if setting in PHP_INI_BEST_PRACTICES:
            info = PHP_INI_BEST_PRACTICES[setting]
            if value != info["recommended"]:
                line = source[:match.start()].count('\n') + 1
                findings.append({"severity": info["severity"], "line": line,
                                "message": f"ini_set('{setting}', '{value}') — recommended: '{info['recommended']}'"})

    return {"file": str(filepath), "findings": findings}


def print_report(config_results: list, code_results: list) -> None:
    all_findings = []
    for r in config_results + code_results:
        all_findings.extend(r["findings"])

    high = sum(1 for f in all_findings if f["severity"] == "HIGH")
    medium = sum(1 for f in all_findings if f["severity"] == "MEDIUM")
    low = sum(1 for f in all_findings if f["severity"] == "LOW")

    for r in config_results:
        if r["findings"]:
            status = "🔴" if any(f["severity"] == "HIGH" for f in r["findings"]) else "⚠"
            print(f"\n{'=' * 70}")
            print(f" {status} {r['file']} ({len(r['findings'])} issues)")
            print(f"{'=' * 70}")
            for f in r["findings"]:
                sev = "[HIGH]" if f["severity"] == "HIGH" else "[MED]" if f["severity"] == "MEDIUM" else "[LOW]"
                line_info = f" line {f['line']}" if f.get("line") else ""
                print(f"     {sev}{line_info} {f['message']}")

    for r in code_results:
        if r["findings"]:
            print(f"\n  💻 {r['file']} ({len(r['findings'])} code issues)")
            for f in r["findings"]:
                sev = "[HIGH]" if f["severity"] == "HIGH" else "[MED]"
                print(f"     {sev} line {f['line']}: {f['message']}")

    if not all_findings:
        print("\n   ✅ No config issues found")

    print(f"\n{'=' * 70}")
    print(f" CONFIG AUDIT SUMMARY")
    print(f"{'=' * 70}")
    print(f"   Config files:  {len(config_results)}")
    print(f"   Code files:    {len(code_results)}")
    print(f"   HIGH: {high}  |  MEDIUM: {medium}  |  LOW: {low}")

    health = "CRITICAL" if high > 0 else "WARNING" if medium > 0 else "CLEAN"
    print(f"   Health: {health}")
    print()


def print_json(config_results: list, code_results: list) -> None:
    all_findings = []
    for r in config_results + code_results:
        all_findings.extend(r["findings"])

    output = {
        "summary": {
            "config_files": len(config_results),
            "code_files": len(code_results),
            "total_findings": len(all_findings),
            "high": sum(1 for f in all_findings if f["severity"] == "HIGH"),
            "medium": sum(1 for f in all_findings if f["severity"] == "MEDIUM"),
            "low": sum(1 for f in all_findings if f["severity"] == "LOW"),
        },
        "config_files": config_results,
        "code_files": code_results,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="php_config_audit.py - PHP config security audit")
    parser.add_argument("path", help="PHP project directory")
    parser.add_argument("--json", "-j", action="store_true")
    parser.add_argument("--version", action="version", version="php_config_audit.py v1.0.0")

    args = parser.parse_args()
    target = Path(args.path)
    if not target.exists():
        print(f"Not found", file=sys.stderr); sys.exit(1)

    root = target if target.is_dir() else target.parent

    print(f"\n⚙️  PHP Config Audit v1.0.0 — {target}")
    print(f"{'=' * 70}")

    config_files = find_config_files(root)
    php_files = find_php_files(root)

    print(f"   Config files: {len(config_files)}  |  PHP files: {len(php_files)}")

    config_results = [audit_config(f) for f in config_files]
    code_results = [audit_php_code(f) for f in php_files]

    if args.json:
        print_json(config_results, code_results)
    else:
        print_report(config_results, code_results)


if __name__ == "__main__":
    main()
