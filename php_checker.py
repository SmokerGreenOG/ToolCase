#!/usr/bin/env python3
"""
php_checker.py — PHP code quality & security checker.

Scant PHP-bestanden en projecten op:
  - Syntax validatie (php -l integratie)
  - Security issues: SQL injection, XSS, file inclusion, command injection,
    eval, hardcoded secrets, unsafe unserialize
  - Code quality: line length, trailing whitespace, TODO/FIXME
  - PHP-specifiek: short open tags, deprecated mysql_*, display_errors,
    error suppression, dangerous functions, extract/parse_str misbruik

Gebruik:
    python php_checker.py <file.php>
    python php_checker.py <directory> --recursive
    python php_checker.py <directory> --recursive --json
    python php_checker.py <file.php> --limit 120
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_MAX_LINE_LENGTH = 120

EXCLUDE_DIRS = {
    "node_modules", "vendor", ".git", "__pycache__",
    ".venv", "venv", "dist", "build", ".cache",
    "storage", "bootstrap/cache", "wp-content/cache",
}

PHP_VERSION = shutil.which("php")  # Path to PHP binary or None

# ══════════════════════════════════════════════════════════════════════════════
# HIGH risk security patterns  (using double-quoted raw strings for safety)
# ══════════════════════════════════════════════════════════════════════════════

HIGH_RISK_PATTERNS = {
    "sql_injection_concat": re.compile(
        r"(?:mysql_query|mysqli_query|pg_query|sqlite_query|odbc_exec|mssql_query)"
        r"\s*\(\s*(?:\$|\"|').*?(?:\$[a-zA-Z_]\w*|\$_GET|\$_POST|\$_REQUEST|\$_COOKIE)",
    ),
    "sql_injection_string": re.compile(
        r"[\"'].*?(?:SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\s+.*?[\"']\s*\.\s*\$",
        re.IGNORECASE,
    ),
    "xss_reflected": re.compile(
        r"(?:echo|print|printf)\s+\$_(?:GET|POST|REQUEST|COOKIE|SERVER)"
        r"(?!.*\bhtmlspecialchars\b)",
    ),
    "xss_raw": re.compile(
        r"(?:echo|print|printf)\s+\$_(?:GET|POST|REQUEST|COOKIE|SERVER)",
    ),
    "file_inclusion": re.compile(
        r"(?:include|require|include_once|require_once)\s*\(?\s*\$"
        r"(?:_(?:GET|POST|REQUEST|COOKIE)|[a-zA-Z_])",
    ),
    "command_injection": re.compile(
        r"(?:system|exec|passthru|shell_exec|popen|proc_open)\s*\("
        r"\s*(?:\$[^,\s)]+|.*?\$_(?:GET|POST|REQUEST))",
    ),
    "backtick_exec": re.compile(
        r"`[^`]*\$\w+[^`]*`",
    ),
    "eval_injection": re.compile(
        r"\beval\s*\(\s*(?:\$|.*?\$)",
    ),
    "assert_code": re.compile(
        r"\bassert\s*\(\s*(?:\$|.*?\$_(?:GET|POST|REQUEST))",
    ),
    "preg_replace_e_modifier": re.compile(
        r"preg_replace\s*\(\s*[\"'].*?/e[\"']",
    ),
    "hardcoded_password": re.compile(
        r"(?i)(?:\$password|\$passwd|\$pass|\$pwd|\$db_pass|"
        r"\$db_password|\$secret|\$api_key|\$apikey|\$token)"
        r"\s*=\s*[\"'][^\"']{4,}[\"']\s*;",
    ),
    "hardcoded_db_creds": re.compile(
        r"(?i)(?:\$db_user|\$username|\$db_host|\$hostname)\s*=\s*[\"'][^\"']{3,}[\"']\s*;",
    ),
    "unsafe_unserialize": re.compile(
        r"\bunserialize\s*\(\s*(?:\$_(?:GET|POST|REQUEST|COOKIE)|\$[a-zA-Z_]\w*)",
    ),
    "create_function": re.compile(
        r"\bcreate_function\s*\(",
    ),
}

# ══════════════════════════════════════════════════════════════════════════════
# MEDIUM risk patterns
# ══════════════════════════════════════════════════════════════════════════════

MEDIUM_RISK_PATTERNS = {
    "extract_on_globals": re.compile(
        r"\bextract\s*\(\s*\$(?:_GET|_POST|_REQUEST|_COOKIE)",
    ),
    "parse_str_no_arg2": re.compile(
        r"\bparse_str\s*\(\s*(?:\$_(?:GET|POST|REQUEST|COOKIE)|\$[a-zA-Z_])\s*\)",
    ),
    "md5_for_password": re.compile(
        r"\bmd5\s*\(\s*(?:\$password|\$pass|\$pwd)",
        re.IGNORECASE,
    ),
    "sha1_for_password": re.compile(
        r"\bsha1\s*\(\s*(?:\$password|\$pass|\$pwd)",
        re.IGNORECASE,
    ),
    "php_self_xss": re.compile(
        r"\$_SERVER\s*\[\s*[\"']PHP_SELF[\"']\s*\]"
        r"(?!.*\bhtmlspecialchars\b)",
    ),
    "file_get_contents_user_input": re.compile(
        r"\bfile_get_contents\s*\(\s*(?:\$_(?:GET|POST|REQUEST)|\$[a-zA-Z_]\w*)",
    ),
    "no_csrf_token": re.compile(
        r"(?i)<form\s[^>]*method\s*=\s*[\"']post[\"'][^>]*>"
        r"(?!.*?(?:csrf|token|nonce|wp_nonce))",
    ),
}

# ══════════════════════════════════════════════════════════════════════════════
# Code quality patterns
# ══════════════════════════════════════════════════════════════════════════════

CODE_QUALITY_PATTERNS = {
    "short_open_tag": re.compile(
        r"<\?(?!php|xml|=)",
    ),
    "display_errors_on": re.compile(
        r"(?i)(?:ini_set|error_reporting)\s*\(\s*[\"'](?:display_errors|error_reporting)[\"']"
        r"\s*,\s*(?:1|true|E_ALL|\"1\"|\"on\")",
    ),
    "error_reporting_all": re.compile(
        r"(?i)error_reporting\s*\(\s*(?:E_ALL|-1)\s*\)",
    ),
    "deprecated_mysql": re.compile(
        r"\bmysql_\w+\s*\(",
    ),
    "error_suppression": re.compile(
        r"@\w+\s*\(",
    ),
    "var_dump_production": re.compile(
        r"\bvar_dump\s*\(",
    ),
    "print_r_production": re.compile(
        r"\bprint_r\s*\(",
    ),
    "die_debug": re.compile(
        r"\bdie\s*\(\s*(?:\$|\".*?\"|'.*?')\s*\)",
    ),
    "nested_ternary": re.compile(
        r"\?.*?\?.*?:.*?:",
    ),
}

# ══════════════════════════════════════════════════════════════════════════════
# Fix suggestions
# ══════════════════════════════════════════════════════════════════════════════

FIX_SUGGESTIONS = {
    "sql_injection_concat": "Use prepared statements (PDO::prepare + bindParam, or mysqli_prepare + bind_param)",
    "sql_injection_string": "Never concatenate user input into SQL strings. Use parameterized queries with PDO or MySQLi",
    "xss_reflected": "Wrap output in htmlspecialchars($var, ENT_QUOTES, 'UTF-8') before echoing",
    "xss_raw": "Always sanitize output: echo htmlspecialchars($_GET['key'], ENT_QUOTES, 'UTF-8')",
    "file_inclusion": "Never include/require files based on user input. Use a whitelist of allowed files",
    "command_injection": "Never pass user input to system/exec/passthru/shell_exec. Use escapeshellarg() if unavoidable",
    "backtick_exec": "Backtick operator executes shell commands - avoid with user input",
    "eval_injection": "Never call eval() with user-supplied data. There is always a safer alternative",
    "assert_code": "assert() can execute code - avoid in production or never pass dynamic strings",
    "preg_replace_e_modifier": "The /e modifier is deprecated and dangerous - use preg_replace_callback() instead",
    "hardcoded_password": "Move credentials to .env or environment variables - never hardcode secrets",
    "hardcoded_db_creds": "Use .env or config files outside web root - never hardcode in PHP files",
    "unsafe_unserialize": "Never unserialize() user input - can lead to object injection attacks. Use JSON instead",
    "create_function": "create_function() is deprecated since PHP 7.2 and uses eval internally. Use anonymous functions",
    "extract_on_globals": "extract() on $_GET/$_POST overwrites local variables - use explicit assignments",
    "parse_str_no_arg2": "parse_str() without second argument writes to global scope. Always provide an array",
    "md5_for_password": "md5() is cryptographically broken. Use password_hash() with bcrypt",
    "sha1_for_password": "sha1() is cryptographically broken. Use password_hash() with bcrypt",
    "php_self_xss": "$_SERVER['PHP_SELF'] can be exploited for XSS. Wrap in htmlspecialchars()",
    "file_get_contents_user_input": "Validate/sanitize user input before passing to file_get_contents()",
    "no_csrf_token": "Add CSRF token to this form to prevent cross-site request forgery attacks",
    "short_open_tag": "Use <?php instead of <? for better compatibility",
    "display_errors_on": "display_errors should be off in production - exposes sensitive info to users",
    "error_reporting_all": "Showing all errors in production leaks path/DB info. Use error_reporting(0) or log only",
    "deprecated_mysql": "mysql_* functions are removed in PHP 7.0+. Use MySQLi or PDO",
    "error_suppression": "The @ operator hides errors - handle them with try/catch or proper checks instead",
    "var_dump_production": "Remove var_dump() - it's debug output that shouldn't be in production",
    "print_r_production": "Remove print_r() - it's debug output that shouldn't be in production",
    "die_debug": "Remove debug die() statement - use proper error handling instead",
    "nested_ternary": "Nested ternary operators are hard to read. Use if/else or extract to well-named variables",
}

# Labels for report output (short readable names)
PATTERN_LABELS = {
    "sql_injection_concat": "SQL Injection (concat query)",
    "sql_injection_string": "SQL Injection (string concat)",
    "xss_reflected": "XSS (reflected - missing htmlspecialchars)",
    "xss_raw": "XSS (raw echo of user input)",
    "file_inclusion": "File Inclusion (user-controlled path)",
    "command_injection": "Command Injection",
    "backtick_exec": "Backtick command execution",
    "eval_injection": "Code Injection (eval)",
    "assert_code": "Code Execution (assert)",
    "preg_replace_e_modifier": "Dangerous preg_replace /e modifier",
    "hardcoded_password": "Hardcoded password/secret",
    "hardcoded_db_creds": "Hardcoded DB credentials",
    "unsafe_unserialize": "Unsafe unserialize()",
    "create_function": "Deprecated create_function()",
    "extract_on_globals": "extract() on superglobal",
    "parse_str_no_arg2": "parse_str() missing 2nd argument",
    "md5_for_password": "md5() used for password hashing",
    "sha1_for_password": "sha1() used for password hashing",
    "php_self_xss": "PHP_SELF XSS vulnerability",
    "file_get_contents_user_input": "file_get_contents() with user input",
    "no_csrf_token": "Missing CSRF token in form",
    "short_open_tag": "Short open tag (<? instead of <?php)",
    "display_errors_on": "display_errors enabled in production",
    "error_reporting_all": "error_reporting(E_ALL) in production",
    "deprecated_mysql": "Deprecated mysql_* function",
    "error_suppression": "@ error suppression",
    "var_dump_production": "Debug var_dump() in code",
    "print_r_production": "Debug print_r() in code",
    "die_debug": "Debug die() statement",
    "nested_ternary": "Nested ternary operators",
}

# ══════════════════════════════════════════════════════════════════════════════
# Core check function
# ══════════════════════════════════════════════════════════════════════════════


def check_php_syntax(filepath: Path) -> tuple:
    """Validate PHP syntax using php -l if available.
    Returns (syntax_ok: bool, message: str)."""
    if PHP_VERSION is None:
        return (True, "PHP not installed - syntax check skipped")

    try:
        result = subprocess.run(
            [PHP_VERSION, "-l", str(filepath)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = (result.stdout + result.stderr).strip()
        if "No syntax errors detected" in output or "No syntax errors" in output:
            return (True, "OK")
        elif "Errors parsing" in output or "Parse error" in output:
            lines = output.split("\n")
            return (False, lines[-2] if len(lines) >= 2 else output)
        else:
            return (result.returncode == 0, output)
    except subprocess.TimeoutExpired:
        return (True, "PHP syntax check timed out")
    except Exception as e:
        return (True, f"Could not run php -l: {e}")


def check_php_file(filepath: Path, max_line: int, security_only: bool = False) -> dict:
    """Main check function for a single PHP file.
    Returns a dict with all findings."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {
            "file": str(filepath),
            "error": f"Cannot read file: {e}",
            "issues": [],
            "lines": 0,
            "syntax_ok": False,
            "security_high": 0,
            "security_medium": 0,
            "quality": 0,
            "total_issues": 0,
        }

    lines = source.split("\n")
    line_count = len(lines)
    issues = []

    # ═══ Syntax check ═══
    syntax_ok, syntax_msg = check_php_syntax(filepath)

    # ═══ Per-line checks ═══
    for i, line in enumerate(lines, 1):
        stripped = line.rstrip("\r")

        if not security_only:
            # Line length
            if len(stripped) > max_line:
                issues.append({
                    "line": i, "type": "quality", "category": "line_length",
                    "message": f"Line too long ({len(stripped)} > {max_line})",
                })

            # Trailing whitespace
            if stripped != stripped.rstrip():
                issues.append({
                    "line": i, "type": "quality", "category": "trailing_ws",
                    "message": "Trailing whitespace",
                })

            # TODO/FIXME/HACK/XXX/BUG in comments
            comment_match = re.search(
                r"(?://|#|/\*).*?\b(TODO|FIXME|HACK|XXX|BUG)\b",
                stripped, re.IGNORECASE,
            )
            if comment_match:
                issues.append({
                    "line": i, "type": "info", "category": "marker",
                    "message": f"Contains '{comment_match.group(1)}'",
                })

            # Short open tag
            short_match = CODE_QUALITY_PATTERNS["short_open_tag"].search(stripped)
            if short_match and "<?php" not in stripped and "<?" in stripped:
                issues.append({
                    "line": i, "type": "quality", "category": "short_open_tag",
                    "message": "Short open tag - use <?php",
                    "fix": FIX_SUGGESTIONS["short_open_tag"],
                })

            # @ error suppression (skip if in regex or string context)
            if CODE_QUALITY_PATTERNS["error_suppression"].search(stripped):
                issues.append({
                    "line": i, "type": "quality", "category": "error_suppression",
                    "message": "@ error suppression operator",
                    "fix": FIX_SUGGESTIONS["error_suppression"],
                })

            # var_dump / print_r / die debug
            for cat in ["var_dump_production", "print_r_production", "die_debug"]:
                if CODE_QUALITY_PATTERNS[cat].search(stripped):
                    name = cat.replace("_production", "").replace("_", " ")
                    issues.append({
                        "line": i, "type": "quality", "category": cat,
                        "message": f"Debug {name} - remove before production",
                        "fix": FIX_SUGGESTIONS[cat],
                    })
                    break  # one debug marker per line

        # ═══ Security: HIGH risk ═══
        for key, pattern in HIGH_RISK_PATTERNS.items():
            match = pattern.search(stripped)
            if match:
                issues.append({
                    "line": i, "type": "security", "category": key,
                    "severity": "HIGH",
                    "message": PATTERN_LABELS.get(key, key),
                    "fix": FIX_SUGGESTIONS.get(key, ""),
                })

        # ═══ Security: MEDIUM risk ═══
        for key, pattern in MEDIUM_RISK_PATTERNS.items():
            match = pattern.search(stripped)
            if match:
                issues.append({
                    "line": i, "type": "security", "category": key,
                    "severity": "MEDIUM",
                    "message": PATTERN_LABELS.get(key, key),
                    "fix": FIX_SUGGESTIONS.get(key, ""),
                })

        # ═══ Deprecated mysql_* functions ═══
        if not security_only and CODE_QUALITY_PATTERNS["deprecated_mysql"].search(stripped):
            issues.append({
                "line": i, "type": "quality", "category": "deprecated_mysql",
                "message": "Deprecated mysql_* function - use MySQLi or PDO",
                "fix": FIX_SUGGESTIONS["deprecated_mysql"],
            })

        # ═══ Nested ternary ═══
        if not security_only and CODE_QUALITY_PATTERNS["nested_ternary"].search(stripped):
            issues.append({
                "line": i, "type": "quality", "category": "nested_ternary",
                "message": "Nested ternary - hard to read",
                "fix": FIX_SUGGESTIONS["nested_ternary"],
            })

    # ═══ Whole-file checks ═══
    full_source = "\n".join(lines)

    if not security_only:
        # display_errors / error_reporting in production
        if CODE_QUALITY_PATTERNS["display_errors_on"].search(full_source):
            issues.append({
                "line": 0, "type": "quality", "category": "display_errors_on",
                "message": "display_errors enabled - turn off in production",
                "fix": FIX_SUGGESTIONS["display_errors_on"],
            })
        elif CODE_QUALITY_PATTERNS["error_reporting_all"].search(full_source):
            issues.append({
                "line": 0, "type": "quality", "category": "error_reporting_all",
                "message": "error_reporting(E_ALL) - don't show in production",
                "fix": FIX_SUGGESTIONS["error_reporting_all"],
            })

        # EOF newline
        if lines and lines[-1] != "":
            issues.append({
                "line": line_count, "type": "quality", "category": "eof_newline",
                "message": "No newline at end of file",
            })

    # ═══ Compute counts ═══
    security_high = sum(1 for i in issues if i["type"] == "security" and i.get("severity") == "HIGH")
    security_medium = sum(1 for i in issues if i["type"] == "security" and i.get("severity") == "MEDIUM")
    quality = sum(1 for i in issues if i["type"] == "quality")

    # Add syntax error as an issue
    if not syntax_ok:
        issues.insert(0, {
            "line": 0, "type": "error", "category": "syntax",
            "message": f"PHP Syntax Error: {syntax_msg}",
        })

    return {
        "file": str(filepath),
        "issues": issues,
        "lines": line_count,
        "syntax_ok": syntax_ok,
        "syntax_msg": syntax_msg if not syntax_ok else "OK",
        "security_high": security_high,
        "security_medium": security_medium,
        "quality": quality,
        "total_issues": len(issues),
    }


# ══════════════════════════════════════════════════════════════════════════════
# File discovery
# ══════════════════════════════════════════════════════════════════════════════


def discover_php_files(root: Path) -> list:
    """Find all .php files, excluding vendor and other ignored dirs."""
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


# ══════════════════════════════════════════════════════════════════════════════
# Output formatting
# ══════════════════════════════════════════════════════════════════════════════


def print_report(results: list, max_line: int) -> None:
    """Human-readable per-file report with grand summary."""
    total_files = len(results)
    total_issues = 0
    total_high = 0
    total_medium = 0
    total_quality = 0
    total_lines = 0
    syntax_failures = 0

    for report in results:
        total_issues += report.get("total_issues", 0)
        total_high += report.get("security_high", 0)
        total_medium += report.get("security_medium", 0)
        total_quality += report.get("quality", 0)
        total_lines += report.get("lines", 0)
        if not report.get("syntax_ok", True):
            syntax_failures += 1

        filepath = report["file"]
        issues = report.get("issues", [])
        syntax_ok = report.get("syntax_ok", True)
        line_count = report.get("lines", 0)
        high_count = report.get("security_high", 0)

        if not syntax_ok:
            status = "X"
        elif high_count > 0:
            status = "! HIGH"
        elif issues:
            status = "~"
        else:
            status = "OK"

        print(f"\n{'=' * 70}")
        print(f" [{status}] {filepath}")
        print(f"{'=' * 70}")
        print(
            f"   Lines: {line_count}  |  Syntax: {'OK' if syntax_ok else 'ERROR'}"
            f"  |  Issues: {len(issues)}"
        )
        print(
            f"   HIGH: {high_count}  |  MEDIUM: {report.get('security_medium', 0)}"
            f"  |  Quality: {report.get('quality', 0)}"
        )

        if issues:
            print(f"\n   Issues ({len(issues)}):")
            for issue in issues:
                line_str = f"{issue['line']:4d}" if issue["line"] > 0 else "   -"
                sev = issue.get("severity", "")
                sev_icon = {"HIGH": "[HIGH]", "MEDIUM": "[MED]"}.get(sev, "     ")
                print(f"     {line_str} | {sev_icon} {issue['message']}")
                if issue.get("fix"):
                    print(f"          |        Fix: {issue['fix']}")
        else:
            print(f"   No issues found")

    # ═══ Grand Summary ═══
    print(f"\n{'=' * 70}")
    print(f" PHP CHECK SUMMARY")
    print(f"{'=' * 70}")
    print(f"   Files scanned:      {total_files}")
    print(f"   Total lines:        {total_lines}")
    print(f"   Syntax errors:      {syntax_failures}")
    print(f"   Total issues:       {total_issues}")
    print(f"   HIGH severity:      {total_high}")
    print(f"   MEDIUM severity:    {total_medium}")
    print(f"   Quality issues:     {total_quality}")
    print(f"   Max line length:    {max_line}")

    if total_high > 0:
        print(f"\n   HEALTH: CRITICAL - {total_high} HIGH-severity security issues found!")
    elif total_medium > 0:
        print(f"   HEALTH: WARNING - {total_medium} MEDIUM-severity issues to review")
    elif total_issues > 0:
        print(f"   HEALTH: FAIR - {total_issues} quality issues, no security risks")
    elif syntax_failures > 0:
        print(f"   HEALTH: BROKEN - {syntax_failures} files with syntax errors")
    else:
        print(f"   HEALTH: CLEAN - No issues found!")

    print()


def print_json(results: list, max_line: int) -> None:
    """Machine-readable JSON output."""
    total_issues = sum(r.get("total_issues", 0) for r in results)
    total_high = sum(r.get("security_high", 0) for r in results)
    total_medium = sum(r.get("security_medium", 0) for r in results)
    total_quality = sum(r.get("quality", 0) for r in results)
    syntax_failures = sum(1 for r in results if not r.get("syntax_ok", True))

    output = {
        "max_line_length": max_line,
        "php_available": PHP_VERSION is not None,
        "summary": {
            "total_files": len(results),
            "total_lines": sum(r.get("lines", 0) for r in results),
            "total_issues": total_issues,
            "high_severity": total_high,
            "medium_severity": total_medium,
            "quality_issues": total_quality,
            "syntax_errors": syntax_failures,
        },
        "files": [],
    }

    for report in results:
        output["files"].append({
            "file": report["file"],
            "lines": report.get("lines", 0),
            "syntax_ok": report.get("syntax_ok", True),
            "security_high": report.get("security_high", 0),
            "security_medium": report.get("security_medium", 0),
            "quality": report.get("quality", 0),
            "total_issues": report.get("total_issues", 0),
            "issues": [
                {
                    "line": i["line"],
                    "type": i["type"],
                    "severity": i.get("severity", ""),
                    "category": i.get("category", ""),
                    "message": i["message"],
                    "fix": i.get("fix", ""),
                }
                for i in report.get("issues", [])
            ],
        })

    print(json.dumps(output, indent=2, ensure_ascii=False))


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        description="php_checker.py - PHP code quality & security checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python php_checker.py app.php                         # Single file
  python php_checker.py src/ --recursive                # Full project
  python php_checker.py src/ -r --json                  # JSON output
  python php_checker.py src/ -r --limit 100             # Custom line limit
  python php_checker.py src/ -r --security-only          # Security checks only
        """,
    )
    parser.add_argument("path", help="PHP file or directory to scan")
    parser.add_argument("--recursive", "-r", action="store_true",
                        help="Recursively scan directories")
    parser.add_argument("--limit", "-l", type=int, default=DEFAULT_MAX_LINE_LENGTH,
                        help=f"Maximum line length (default: {DEFAULT_MAX_LINE_LENGTH})")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--security-only", action="store_true",
                        help="Only run security checks (skip code quality)")
    parser.add_argument("--version", action="version", version="php_checker.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"'{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    print(f"\nPHP Checker v1.0.0 - scanning: {target}")
    if PHP_VERSION:
        print(f"   PHP binary: {PHP_VERSION}")
    else:
        print(f"   PHP not found in PATH - syntax validation disabled")
    print(f"   Max line length: {args.limit}")
    if args.security_only:
        print(f"   Mode: Security only (skipping code quality)")
    print(f"{'=' * 70}")

    if target.is_file():
        if target.suffix != ".php":
            print(f"Not a .php file: {target}", file=sys.stderr)
            sys.exit(1)
        print(f"1 file found")
        results = [check_php_file(target, args.limit, args.security_only)]

    elif target.is_dir():
        if args.recursive:
            files = discover_php_files(target)
        else:
            files = sorted(target.glob("*.php"))

        if not files:
            print(f"No .php files found in {target}")
            sys.exit(0)

        print(f"{len(files)} PHP file(s) found")
        results = []
        for f in files:
            results.append(check_php_file(f, args.limit, args.security_only))
    else:
        print(f"'{args.path}' is not a file or directory", file=sys.stderr)
        sys.exit(1)

    # Output
    if args.json:
        print_json(results, args.limit)
    else:
        print_report(results, args.limit)


if __name__ == "__main__":
    main()
