#!/usr/bin/env python3
"""
env_check.py — Check environment variables and required config files.

Detects:
  - Required environment variables that are missing
  - Required config files that don't exist
  - .env file issues (missing, malformed, duplicate keys)
  - Recommended but optional settings

Gebruik:
    python env_check.py <path>
    python env_check.py <path> --template .env.example
    python env_check.py <path> --json
    python env_check.py init <path>            # Genereer een .env.example
"""

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import os
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Common environment variable patterns
# ---------------------------------------------------------------------------

COMMON_ENV_VARS = {
    "DATABASE_URL": {"description": "Database connection string", "category": "database"},
    "DB_HOST": {"description": "Database host", "category": "database"},
    "DB_PORT": {"description": "Database port", "category": "database"},
    "DB_NAME": {"description": "Database name", "category": "database"},
    "DB_USER": {"description": "Database user", "category": "database"},
    "DB_PASSWORD": {"description": "Database password", "category": "database"},
    "REDIS_URL": {"description": "Redis connection string", "category": "cache"},
    "REDIS_HOST": {"description": "Redis host", "category": "cache"},
    "REDIS_PORT": {"description": "Redis port", "category": "cache"},
    "API_KEY": {"description": "API key for external service", "category": "auth"},
    "SECRET_KEY": {"description": "Application secret key", "category": "auth"},
    "JWT_SECRET": {"description": "JWT signing secret", "category": "auth"},
    "JWT_EXPIRY": {"description": "JWT token expiry time", "category": "auth"},
    "NODE_ENV": {"description": "Node.js environment (development/production)", "category": "env"},
    "APP_ENV": {"description": "Application environment", "category": "env"},
    "LOG_LEVEL": {"description": "Logging level (debug/info/warn/error)", "category": "logging"},
    "PORT": {"description": "Application port", "category": "network"},
    "HOST": {"description": "Application host", "category": "network"},
    "CORS_ORIGIN": {"description": "Allowed CORS origins", "category": "network"},
    "S3_BUCKET": {"description": "S3 bucket name", "category": "storage"},
    "S3_REGION": {"description": "S3 region", "category": "storage"},
    "S3_ACCESS_KEY": {"description": "S3 access key", "category": "storage"},
    "S3_SECRET_KEY": {"description": "S3 secret key", "category": "storage"},
    "OPENAI_API_KEY": {"description": "OpenAI API key", "category": "ai"},
    "ANTHROPIC_API_KEY": {"description": "Anthropic API key", "category": "ai"},
    "DEEPSEEK_API_KEY": {"description": "DeepSeek API key", "category": "ai"},
    "TELEGRAM_BOT_TOKEN": {"description": "Telegram bot token", "category": "bot"},
    "DISCORD_BOT_TOKEN": {"description": "Discord bot token", "category": "bot"},
    "SLACK_BOT_TOKEN": {"description": "Slack bot token", "category": "bot"},
    "SENDGRID_API_KEY": {"description": "SendGrid API key", "category": "email"},
    "SMTP_HOST": {"description": "SMTP server host", "category": "email"},
    "SMTP_PORT": {"description": "SMTP server port", "category": "email"},
    "SMTP_USER": {"description": "SMTP username", "category": "email"},
    "SMTP_PASS": {"description": "SMTP password", "category": "email"},
}

REQUIRED_FILES = {
    "package.json": "Node.js dependencies",
    "Cargo.toml": "Rust project config",
    "pyproject.toml": "Python project config",
    "requirements.txt": "Python dependencies",
    "tsconfig.json": "TypeScript config",
    "vite.config.ts": "Vite build config",
    "vite.config.js": "Vite build config",
    "tauri.conf.json": "Tauri config",
    "tauri.conf.json5": "Tauri config",
    ".gitignore": "Git ignore rules",
    "docker-compose.yml": "Docker services",
    "Dockerfile": "Docker build",
    "README.md": "Project documentation",
    "LICENSE": "Software license",
}

OPTIONAL_FILES = {
    ".github/workflows": "CI/CD workflows",
    ".husky": "Git hooks",
    ".editorconfig": "Editor config",
    ".prettierrc": "Prettier config",
    ".eslintrc": "ESLint config",
    "jest.config.ts": "Jest config",
    "vitest.config.ts": "Vitest config",
    "Makefile": "Build automation",
    "justfile": "Just task runner",
    "cliff.toml": "Changelog config (git-cliff)",
    ".env.example": "Environment template",
    "CONTRIBUTING.md": "Contribution guide",
    "CHANGELOG.md": "Changelog",
}


def parse_env_file(env_path: Path) -> dict[str, str]:
    """Parse a .env file and return key-value pairs."""
    result = {}
    if not env_path.exists():
        return result

    try:
        content = env_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return result

    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Support export KEY=val syntax
        if line.startswith("export "):
            line = line[7:].strip()

        if "=" not in line:
            continue

        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("\"'")
        result[key] = val

    return result


def extract_referenced_env_vars(root: Path) -> set[str]:
    """Extract environment variable names referenced in source code."""
    refs = set()
    env_pattern = re.compile(
        r'(?:os\.(?:getenv|environ(?:\[|\.get)\s*\()[\s"\']*(\w+)|'
        r"process\.env\.(\w+)|"
        r'env\s*[\[.]\s*["\'](\w+)["\']|'
        r"\$(\w+)\b)"
    )

    EXCLUDE_DIRS = frozenset(
        {
            "node_modules",
            "target",
            ".git",
            "__pycache__",
            ".venv",
            "venv",
            ".backups",
            ".rsi_backups",
            ".rsi_reports",
            ".self_improve_reports",
        }
    )

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            try:
                fp = Path(dirpath) / fn
                content = fp.read_text(encoding="utf-8", errors="replace")
                for m in env_pattern.finditer(content):
                    for g in m.groups():
                        if g and g.isupper() and len(g) > 2:
                            refs.add(g)
            except Exception:
                continue

    return refs


def check_project_dotenv(root: Path) -> list[dict]:
    """Check .env files in the project."""
    issues = []
    env_path = root / ".env"
    env_example = root / ".env.example"

    if not env_path.exists():
        issues.append(
            {
                "severity": "WARN",
                "message": ".env bestand niet gevonden",
                "detail": "Maak een .env bestand aan met je omgevingsvariabelen",
                "fix": f"cp .env.example .env  # als .env.example bestaat",
            }
        )

    if env_path.exists():
        env_vars = parse_env_file(env_path)
        if not env_vars:
            issues.append(
                {
                    "severity": "WARN",
                    "message": ".env bestand is leeg",
                    "detail": "Geen variabelen gevonden in .env",
                }
            )

    if not env_example.exists():
        issues.append(
            {
                "severity": "INFO",
                "message": ".env.example niet gevonden",
                "detail": "Een .env.example helpt andere developers met de juiste variabelen",
                "fix": "python env_check.py init .  # genereer .env.example",
            }
        )

    if env_path.exists() and env_example.exists():
        env_vars = parse_env_file(env_path)
        example_vars = parse_env_file(env_example)
        missing = set(example_vars.keys()) - set(env_vars.keys())
        for var in sorted(missing):
            issues.append(
                {
                    "severity": "WARN",
                    "message": f"Ontbrekende variabele in .env: {var}",
                    "detail": f"Staat wel in .env.example maar niet in .env",
                    "fix": f"Voeg {var} toe aan .env",
                }
            )

        extra = set(env_vars.keys()) - set(example_vars.keys())
        for var in sorted(extra):
            issues.append(
                {
                    "severity": "INFO",
                    "message": f"Extra variabele in .env (niet in .env.example): {var}",
                    "detail": "Overweeg om deze aan .env.example toe te voegen",
                }
            )

    return issues


def check_required_files(root: Path) -> list[dict]:
    """Check for required project files."""
    issues = []
    for filename, description in REQUIRED_FILES.items():
        if not (root / filename).exists():
            issues.append(
                {
                    "severity": "WARN",
                    "message": f"Ontbrekend bestand: {filename}",
                    "detail": f"({description})",
                    "fix": f"Maak een {filename} aan in de project root",
                }
            )
    return issues


def check_env_references(root: Path) -> list[dict]:
    """Cross-reference used env vars with .env file."""
    issues = []
    env_path = root / ".env"
    env_vars = parse_env_file(env_path) if env_path.exists() else {}
    referenced = extract_referenced_env_vars(root)

    missing = referenced - set(env_vars.keys()) - set(os.environ.keys())
    for var in sorted(missing):
        info = COMMON_ENV_VARS.get(var, {})
        desc = info.get("description", "Onbekende variabele")
        cat = info.get("category", "general")
        issues.append(
            {
                "severity": "WARN",
                "message": f"Gebruikte maar niet-gedefinieerde env var: {var}",
                "detail": f"Categorie: {cat} — {desc}",
                "fix": f"Voeg {var}=<waarde> toe aan .env",
            }
        )

    defined_env = set(env_vars.keys()) | set(os.environ.keys())
    unused = defined_env - referenced - {"PATH", "HOME", "USER", "SHELL", "TERM", "LANG"}
    for var in sorted(unused):
        issues.append(
            {
                "severity": "INFO",
                "message": f"Ongebruikte env var in .env: {var}",
                "detail": "Wordt nergens in de code gerefereerd",
                "fix": f"Overweeg om {var} uit .env te verwijderen",
            }
        )

    return issues


def check_common_vars(root: Path) -> list[dict]:
    """Check which common env vars are missing."""
    issues = []
    env_path = root / ".env"
    env_vars = parse_env_file(env_path) if env_path.exists() else {}

    defined = set(env_vars.keys()) | set(os.environ.keys())

    # Group by category
    by_category = {}
    for var, info in COMMON_ENV_VARS.items():
        by_category.setdefault(info["category"], []).append(var)

    cat_names = {
        "database": "Database",
        "cache": "Cache/Redis",
        "auth": "Authenticatie/Secrets",
        "env": "Omgeving",
        "logging": "Logging",
        "network": "Netwerk",
        "storage": "Storage",
        "ai": "AI/LLM",
        "bot": "Bots",
        "email": "Email",
    }

    for cat, vars_in_cat in by_category.items():
        present = [v for v in vars_in_cat if v in defined]
        if present:
            # Check if typical vars for this category are missing
            typical_missing = [v for v in vars_in_cat if v not in defined]
            for var in typical_missing:
                info = COMMON_ENV_VARS[var]
                issues.append(
                    {
                        "severity": "INFO",
                        "message": f"Mogelijk ontbrekende {cat_names.get(cat, cat)} var: {var}",
                        "detail": info["description"],
                        "fix": f"Overweeg {var}=<waarde> in .env (indien van toepassing)",
                    }
                )

    return issues


def generate_env_example(root: Path) -> None:
    """Generate a .env.example file based on common patterns and source code references."""
    print(f"\n🔧 Genereer .env.example in {root}...")

    referenced = extract_referenced_env_vars(root)
    known_vars = set(COMMON_ENV_VARS.keys())
    all_vars = referenced | known_vars

    if not all_vars:
        print(" Geen environment variabelen gevonden.")
        return

    # Sort: database first, then auth, then rest
    category_order = [
        "database",
        "auth",
        "cache",
        "ai",
        "bot",
        "network",
        "storage",
        "email",
        "logging",
        "env",
        "general",
    ]
    by_cat_order = {}
    for var in all_vars:
        info = COMMON_ENV_VARS.get(var, {})
        cat = info.get("category", "general")
        cat_order = category_order.index(cat) if cat in category_order else 99
        desc = info.get("description", "")
        by_cat_order.setdefault(cat_order, []).append((var, cat, desc))

    cat_names = {
        "database": "# ── Database ──",
        "cache": "# ── Cache ──",
        "auth": "# ── Authenticatie / Secrets ──",
        "env": "# ── Omgeving ──",
        "logging": "# ── Logging ──",
        "network": "# ── Netwerk ──",
        "storage": "# ── Storage ──",
        "ai": "# ── AI / LLM ──",
        "bot": "# ── Bots ──",
        "email": "# ── Email ──",
        "general": "# ── Overige ──",
    }

    lines = [
        "# .env.example — Environment variabelen template",
        "# Kopieer naar .env en vul de waarden in:",
        "#   cp .env.example .env",
        "",
    ]

    for cat_order in sorted(by_cat_order.keys()):
        items = by_cat_order[cat_order]
        # Find the category name for the first item
        first_cat = items[0][1]
        header = cat_names.get(first_cat, f"# ── {first_cat.upper()} ──")
        lines.append(header)
        for var, cat, desc in sorted(items):
            if desc:
                lines.append(f"# {desc}")
            lines.append(f"{var}=")
            lines.append("")
        lines.append("")

    example_path = root / ".env.example"
    example_path.write_text("\n".join(lines), encoding="utf-8")
    print(f" ✅ .env.example gegenereerd met {len(all_vars)} variabelen → {example_path}")


def print_results(
    env_issues: list[dict],
    file_issues: list[dict],
    ref_issues: list[dict],
    common_issues: list[dict],
) -> None:
    """Print all results in a formatted way."""
    all_issues = env_issues + file_issues + ref_issues + common_issues
    warnings = [i for i in all_issues if i["severity"] == "WARN"]
    infos = [i for i in all_issues if i["severity"] == "INFO"]

    print(f"\n{'=' * 60}")
    print(f" 🌍 ENVIRONMENT CHECK")
    print(f"{'=' * 60}")
    print(f"   ⚠  Warnings: {len(warnings)}")
    print(f"   💡 Info:     {len(infos)}")
    print()

    if env_issues:
        print(f"\n ── .env Bestand ──")
        for issue in env_issues:
            icon = "⚠" if issue["severity"] == "WARN" else "💡"
            print(f"   {icon} {issue['message']}")
            print(f"      {issue['detail']}")
            if issue.get("fix"):
                print(f"      🔧 {issue['fix']}")

    if file_issues:
        print(f"\n ── Project Bestanden ──")
        for issue in file_issues:
            print(f"   ⚠ {issue['message']}")
            print(f"      {issue['detail']}")
            if issue.get("fix"):
                print(f"      🔧 {issue['fix']}")

    if ref_issues:
        print(f"\n ── Env Variabelen Referenties ──")
        for issue in ref_issues:
            icon = "⚠" if issue["severity"] == "WARN" else "💡"
            print(f"   {icon} {issue['message']}")
            print(f"      {issue['detail']}")
            if issue.get("fix"):
                print(f"      🔧 {issue['fix']}")

    if common_issues:
        print(f"\n ── Aanbevolen Variabelen ──")
        for issue in common_issues:
            print(f"   💡 {issue['message']}")
            print(f"      {issue['detail']}")

    if not all_issues:
        print(" ✅ Alles ziet er goed uit!")

    print()


def main() -> None:
    """main."""
    parser = argparse.ArgumentParser(
        description="env_check.py — Check environment variables and config files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python env_check.py                          # Check current project
  python env_check.py check .                  # Check current project
  python env_check.py check . --template .env.example
  python env_check.py . --json                 # JSON output
  python env_check.py init .                   # Generate .env.example
        """,
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="check",
        help="'check' (default) of 'init' (genereer .env.example)",
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root directory")
    parser.add_argument("--template", "-t", help="Path to .env.example template")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--version", action="version", version="env_check.py v1.0.0")

    args = parser.parse_args()

    # Smart detect: if first arg looks like a path, swap
    target_path = args.path
    target_action = args.action
    if target_action not in ("check", "init") and Path(target_action).exists():
        target_path = target_action
        target_action = "check"
    elif Path(target_path).exists():
        pass  # Normal case
    else:
        # Try swapping
        if Path(target_action).exists():
            target_path = target_action
            target_action = "check"

    target = Path(target_path).resolve()
    if not target.exists():
        print(f" ❌ '{target_path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    if target_action == "init":
        generate_env_example(target)
        return

    if target_action != "check":
        print(
            f" ❌ Onbekende actie: '{target_action}'. Gebruik 'check' of 'init'.", file=sys.stderr
        )
        sys.exit(1)

    print(f"\n🔍 Environment Check v1.0.0 — {target}")

    env_issues = check_project_dotenv(target)
    file_issues = check_required_files(target)
    ref_issues = check_env_references(target)
    common_issues = check_common_vars(target)

    if args.json:
        output = {
            "env_issues": env_issues,
            "file_issues": file_issues,
            "ref_issues": ref_issues,
            "common_issues": common_issues,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print_results(env_issues, file_issues, ref_issues, common_issues)


if __name__ == "__main__":
    main()
