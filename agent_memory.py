#!/usr/bin/env python3
"""
agent_memory.py — Track Hermes agent configuration, state, and memory.

Analyzes:
  - Hermes agent config (config.yaml, profiles)
  - Installed skills and their versions
  - Active plugins and tools
  - Memory usage and content
  - Session logs and history
  - Cron jobs and scheduled tasks

Gebruik:
    python agent_memory.py                              # Track current agent state
    python agent_memory.py --config                     # Show config summary
    python agent_memory.py --skills                     # List installed skills
    python agent_memory.py --session                    # Show session info
    python agent_memory.py --json                       # JSON output
"""

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Standard Hermes paths
HERMES_HOME = Path.home() / "AppData" / "Local" / "hermes"
HERMES_CONFIG = HERMES_HOME / "config.yaml"
HERMES_PROFILES = HERMES_HOME / "profiles"
HERMES_SKILLS = HERMES_HOME / "skills"
HERMES_PLUGINS = HERMES_HOME / "plugins"
HERMES_MEMORY = HERMES_HOME / "memory"
HERMES_CRON = HERMES_HOME / "cron"
HERMES_LOGS = HERMES_HOME / "logs"


def get_config_info() -> dict:
    """Read and summarize Hermes config."""
    info = {"config_files": [], "has_config": False, "providers": [], "profiles": []}

    if HERMES_CONFIG.exists():
        info["has_config"] = True
        info["config_files"].append(str(HERMES_CONFIG))
        try:
            content = HERMES_CONFIG.read_text(encoding="utf-8")
            # Extract provider names
            skip_keys = {
                "default",
                "profiles",
                "memory",
                "skills",
                "plugins",
                "cron",
                "logging",
                "session",
            }
            for m in re.finditer(r"^(\w+):", content, re.MULTILINE):
                provider = m.group(1)
                if provider not in skip_keys:
                    info["providers"].append(provider)
        except Exception:
            pass

    # Check profiles
    if HERMES_PROFILES.exists():
        try:
            profiles = sorted(d.name for d in HERMES_PROFILES.iterdir() if d.is_dir())
            info["profiles"] = profiles
        except Exception:
            pass

    return info


def get_skills_info() -> list[dict]:
    """List installed Hermes skills."""
    skills = []
    if not HERMES_SKILLS.exists():
        return skills

    try:
        for path in sorted(HERMES_SKILLS.iterdir()):
            if path.is_dir():
                skill_md = path / "SKILL.md"
                if skill_md.exists():
                    try:
                        content = skill_md.read_text(encoding="utf-8")
                        # Extract name and description from frontmatter
                        name_match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
                        desc_match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
                        skill_name = name_match.group(1).strip() if name_match else path.name
                        description = desc_match.group(1).strip() if desc_match else ""
                        skills.append(
                            {
                                "name": skill_name,
                                "path": str(path),
                                "description": description,
                                "size": sum(
                                    f.stat().st_size for f in path.rglob("*") if f.is_file()
                                ),
                            }
                        )
                    except Exception:
                        skills.append({"name": path.name, "path": str(path)})
    except Exception:
        pass

    return skills


def get_memory_info() -> dict:
    """Read Hermes memory content summary."""
    info = {"total_entries": 0, "categories": {}, "memory_files": []}

    if not HERMES_MEMORY.exists():
        return info

    try:
        for f in sorted(HERMES_MEMORY.rglob("*")):
            if f.is_file() and f.suffix in (".md", ".txt", ".json", ".yaml", ".yml"):
                info["memory_files"].append(str(f))
                rel = f.relative_to(HERMES_MEMORY)
                cat = rel.parts[0] if len(rel.parts) > 1 else "root"
                info["categories"][cat] = info["categories"].get(cat, 0) + 1
                info["total_entries"] += 1
    except Exception:
        pass

    return info


def get_session_info() -> dict:
    """Get current session info."""
    # This script itself doesn't have access to the live session,
    # but it can check the session database
    info = {
        "toolcase_dir": str(Path.cwd()),
        "timestamp": datetime.now().isoformat(),
        "python_version": sys.version,
    }
    return info


def get_plugins_info() -> list[dict]:
    """List installed Hermes plugins."""
    plugins = []
    if not HERMES_PLUGINS.exists():
        return plugins

    try:
        for path in sorted(HERMES_PLUGINS.iterdir()):
            if path.is_dir():
                plugin_yaml = path / "plugin.yaml"
                if plugin_yaml.exists():
                    try:
                        content = plugin_yaml.read_text(encoding="utf-8")
                        name_match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
                        plugin_name = name_match.group(1).strip() if name_match else path.name
                        plugins.append({"name": plugin_name, "path": str(path)})
                    except Exception:
                        plugins.append({"name": path.name, "path": str(path)})
    except Exception:
        pass

    return plugins


def get_cron_info() -> list[dict]:
    """List scheduled cron jobs."""
    jobs = []
    if not HERMES_CRON.exists():
        return jobs

    try:
        for f in sorted(HERMES_CRON.iterdir()):
            if f.is_file() and f.suffix in (".json", ".yaml", ".yml"):
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    jobs.append({"file": f.name, "content_preview": content[:200]})
                except Exception:
                    jobs.append({"file": f.name})
    except Exception:
        pass

    return jobs


def print_report(
    config: dict,
    skills: list[dict],
    memory: dict,
    session: dict,
    plugins: list[dict],
    cron: list[dict],
) -> None:
    """Print a formatted agent state report."""
    print(f"\n{'=' * 60}")
    print(f" 🧠 AGENT MEMORY TRACKER")
    print(f"{'=' * 60}")
    print(f"   Hermes home: {HERMES_HOME}")
    print(f"   Timestamp:   {session.get('timestamp', '?')}")
    print()

    # Config
    print(f" ── Config ──")
    if config["has_config"]:
        print(f"   ✅ Config bestand gevonden: {config['config_files'][0]}")
        if config["providers"]:
            print(f"   Providers: {', '.join(config['providers'][:5])}")
        if config["profiles"]:
            print(f"   Profiles: {', '.join(config['profiles'])}")
    else:
        print(f"   ⚠  Geen config.yaml gevonden onder {HERMES_CONFIG}")
    print()

    # Skills
    print(f" ── Skills ({len(skills)}) ──")
    for s in skills[:10]:
        size_kb = s.get("size", 0) / 1024 if s.get("size") else 0
        desc = f" — {s['description'][:60]}" if s.get("description") else ""
        print(f"   📦 {s['name']}{desc} ({size_kb:.0f} KB)")
    if len(skills) > 10:
        print(f"   ... en nog {len(skills) - 10} skills")
    print()

    # Memory
    print(f" ── Memory ({memory['total_entries']} entries) ──")
    for cat, count in sorted(memory.get("categories", {}).items()):
        print(f"   🗂  {cat}: {count} bestand(en)")
    print()

    # Plugins
    if plugins:
        print(f" ── Plugins ({len(plugins)}) ──")
        for p in plugins:
            print(f"   🔌 {p['name']}")
        print()

    # Cron
    if cron:
        print(f" ── Cron Jobs ({len(cron)}) ──")
        for c in cron:
            print(f"   ⏰ {c['file']}")
        print()

    print(f" ── Python ──")
    print(f"   🐍 Python {session.get('python_version', '?')}")
    print(f"   📁 Werkdirectory: {session.get('toolcase_dir', '?')}")
    print()


def main() -> None:
    """main."""
    parser = argparse.ArgumentParser(
        description="agent_memory.py — Track Hermes agent configuration and state",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python agent_memory.py                 # Full report
  python agent_memory.py --config        # Config only
  python agent_memory.py --skills        # Skills only
  python agent_memory.py --json          # JSON output
        """,
    )
    parser.add_argument("--config", "-c", action="store_true", help="Toon config info")
    parser.add_argument("--skills", "-s", action="store_true", help="Toon skills")
    parser.add_argument("--session", action="store_true", help="Toon session info")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--version", action="version", version="agent_memory.py v1.0.0")

    args = parser.parse_args()

    if args.json:
        output = {
            "hermes_home": str(HERMES_HOME),
            "config": get_config_info(),
            "skills": get_skills_info(),
            "memory": get_memory_info(),
            "session": get_session_info(),
            "plugins": get_plugins_info(),
            "cron": get_cron_info(),
        }
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    elif args.config:
        config = get_config_info()
        print(json.dumps(config, indent=2))
    elif args.skills:
        skills = get_skills_info()
        print(json.dumps(skills, indent=2))
    elif args.session:
        session = get_session_info()
        print(json.dumps(session, indent=2, default=str))
    else:
        config = get_config_info()
        skills = get_skills_info()
        memory = get_memory_info()
        session = get_session_info()
        plugins = get_plugins_info()
        cron = get_cron_info()
        print_report(config, skills, memory, session, plugins, cron)

    sys.exit(0)


if __name__ == "__main__":
    main()
