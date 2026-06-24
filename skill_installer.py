#!/usr/bin/env python3
"""
skill_installer.py — Installeert en valideert Hermes/Sabine skills.

Controleert:
  - Skill folder structuur (metadata, commands/, prompts/)
  - metadata.json of skill.yaml aanwezigheid en validiteit
  - Commands en prompts bestaan
  - Permissies (read_only, needs_approval, safety rules)
  - Tool dependencies zijn geïnstalleerd
  - Test command is aanwezig (indien gespecificeerd)
  - Registry update nodig?

Gebruik:
    python skill_installer.py install <skill_name_or_path>   # Installeer skill
    python skill_installer.py validate <skill_path>           # Valideer skill structuur
    python skill_installer.py test <skill_name>               # Run skill tests
    python skill_installer.py list                            # Toon geïnstalleerde skills
    python skill_installer.py --help                          # Dit help scherm
    python skill_installer.py --json                          # JSON output
"""
__maker__ = "SmokerGreenOG"

import _protect

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import textwrap
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

# Standard Hermes skill registry locations
SKILL_REGISTRY_CANDIDATES = [
    Path.home() / ".hermes" / "skills",
    Path.home() / ".config" / "hermes" / "skills",
    Path.home() / ".local" / "share" / "hermes" / "skills",
    Path("/etc/hermes/skills"),
]

# Required subdirectories for a valid skill
REQUIRED_SKILL_DIRS = {"commands", "prompts"}

# Valid metadata filenames
METADATA_FILENAMES = {"metadata.json", "skill.yaml", "skill.yml"}

# Valid extensions for command files
COMMAND_EXTENSIONS = {".py", ".sh", ".ps1", ".bat", ".js", ".ts", ".lua"}

# Directories/files to skip during traversal
EXCLUDE_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".tox", ".eggs", "build", "dist", ".next", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".cursor",
    ".backups",
    ".rsi_backups",
    ".rsi_reports",
    ".self_improve_reports",
})

# Generated report files to skip in security scans and other tools
GENERATED_REPORT_GLOBS = (
    "*_audit_report.md",
    "*_audit_report.html",
    "*.rsi_reports/*",
    "*.self_improve_reports/*",
    "*.rsi_backups/*",
    "codex_audit_report.*",
)

# ToolCase tools available for dependency checking
TOOLCASE_TOOLS = frozenset({
    "improve.py", "security_scan.py", "env_check.py", "project_doctor.py",
    "route_scanner.py", "frontend_backend_linker.py", "dead_code_finder.py",
    "todo_tracker.py", "test_runner.py", "patch_preview.py", "rollback.py",
    "dependency_audit.py", "workspace_indexer.py", "agent_memory.py",
    "ui_consistency.py", "feature_gap_analyzer.py", "multiscan.py",
    "complexity.py", "depgraph.py", "command_guard.py", "file_guard.py",
    "permission_audit.py", "api_contract_checker.py", "fake_ui_detector.py",
    "button_action_scanner.py", "state_inspector.py", "build_doctor.py",
    "log_viewer.py", "error_explainer.py", "release_packager.py",
    "changelog_generator.py", "skill_installer.py",
})


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _find_registry() -> Optional[Path]:
    """Find the first existing Hermes skill registry directory."""
    for candidate in SKILL_REGISTRY_CANDIDATES:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _ensure_registry() -> Path:
    """Ensure the primary skill registry exists, create if needed."""
    primary = SKILL_REGISTRY_CANDIDATES[0]  # ~/.hermes/skills/
    primary.mkdir(parents=True, exist_ok=True)
    return primary


def _registry_file() -> Path:
    """Path to the registry index file."""
    registry_dir = _ensure_registry()
    return registry_dir / "_registry_index.json"


def _read_registry_index() -> dict[str, Any]:
    """Read the registry index, return empty dict if missing."""
    rfile = _registry_file()
    if rfile.exists():
        try:
            with open(rfile, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_registry_index(index: dict[str, Any]) -> None:
    """Write the registry index."""
    rfile = _registry_file()
    with open(rfile, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def _load_json(path: Path) -> Optional[dict[str, Any]]:
    """Load a JSON file, return None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def _load_yaml(path: Path) -> Optional[dict[str, Any]]:
    """Load a YAML file using a basic parser (avoids pyyaml dependency)."""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    # Simple YAML parser for skill metadata (flat-ish structure)
    data: dict[str, Any] = {}
    current_key: Optional[str] = None
    list_buffer: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()

        # Skip comments and blank lines
        if not stripped or stripped.startswith("#"):
            continue

        # Multi-line list items under a key
        if stripped.startswith("- "):
            if current_key:
                list_buffer.append(stripped[2:].strip().strip('"').strip("'"))
            continue

        # Key: value pair
        if ":" in stripped:
            # Save previous list if any
            if current_key and list_buffer:
                data[current_key] = list_buffer
                list_buffer = []
                current_key = None

            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")

            if not val:
                # This might be a list header
                current_key = key
                list_buffer = []
            else:
                # Parse boolean and None
                if val.lower() in ("true", "yes", "on"):
                    val = True
                elif val.lower() in ("false", "no", "off"):
                    val = False
                elif val.lower() == "null" or val == "~":
                    val = None
                elif val.isdigit():
                    val = int(val)
                elif re.match(r"^\d+\.\d+$", val):
                    val = float(val)
                data[key] = val

    # Flush remaining list buffer
    if current_key and list_buffer:
        data[current_key] = list_buffer

    return data if data else None


def _load_metadata(skill_path: Path) -> Optional[dict[str, Any]]:
    """Load skill metadata from metadata.json or skill.yaml/skill.yml."""
    for fname in METADATA_FILENAMES:
        fpath = skill_path / fname
        if fpath.exists():
            if fname.endswith(".json"):
                return _load_json(fpath)
            else:
                return _load_yaml(fpath)
    return None


def _find_installed_skills() -> dict[str, Path]:
    """Discover all installed skills by scanning registry directories."""
    skills: dict[str, Path] = {}
    registry = _find_registry()
    if not registry:
        return skills

    for entry in sorted(registry.iterdir()):
        if entry.is_dir() and not entry.name.startswith("_"):
            metadata = _load_metadata(entry)
            if metadata:
                name = metadata.get("name", entry.name)
                skills[name] = entry
            else:
                # Even without metadata, treat directory as a skill if it has commands/
                if (entry / "commands").exists():
                    skills[entry.name] = entry

    # Also check the registry index for symlinked/registered skills
    index = _read_registry_index()
    for name, info in index.items():
        if name not in skills:
            path_str = info.get("path", "")
            p = Path(path_str)
            if p.exists() and p.is_dir():
                skills[name] = p

    return skills


def _print_json(data: Any) -> None:
    """Print output as JSON."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_skill(skill_path: Path, fix: bool = False) -> list[dict]:
    """
    Validate a skill directory structure and contents.

    Returns a list of issue dicts with keys:
      severity: "ERROR" | "WARN" | "INFO"
      type: str
      message: str
      fix: Optional[str]
    """
    issues: list[dict] = []

    if not skill_path.exists():
        issues.append({
            "severity": "ERROR",
            "type": "exists",
            "message": f"Skill pad bestaat niet: {skill_path}",
        })
        return issues

    if not skill_path.is_dir():
        issues.append({
            "severity": "ERROR",
            "type": "exists",
            "message": f"Skill pad is geen directory: {skill_path}",
        })
        return issues

    # ── Check 1: Metadata file ────────────────────────────────────
    metadata = _load_metadata(skill_path)
    metadata_file = None
    for fname in METADATA_FILENAMES:
        if (skill_path / fname).exists():
            metadata_file = skill_path / fname
            break

    if metadata_file is None:
        issues.append({
            "severity": "ERROR",
            "type": "metadata",
            "message": f"Geen metadata bestand gevonden. Verwacht: {', '.join(sorted(METADATA_FILENAMES))}",
            "fix": f"Maak {skill_path / 'metadata.json'} aan met minimaal 'name', 'description' en 'version'",
        })
    elif metadata is None:
        issues.append({
            "severity": "ERROR",
            "type": "metadata",
            "message": f"{metadata_file.name} is ongeldig (parse fout of leeg)",
        })
    else:
        # Validate metadata content
        required_fields = {"name", "description", "version"}
        missing = required_fields - set(metadata.keys())
        if missing:
            issues.append({
                "severity": "ERROR",
                "type": "metadata",
                "message": f"Verplichte velden ontbreken in {metadata_file.name}: {', '.join(sorted(missing))}",
            })

        # Check recommended fields
        recommended = {"author", "commands", "permissions"}
        missing_rec = recommended - set(metadata.keys())
        if missing_rec:
            issues.append({
                "severity": "WARN",
                "type": "metadata",
                "message": f"Aanbevolen velden ontbreken in {metadata_file.name}: {', '.join(sorted(missing_rec))}",
            })

        # Check version format (semver-ish)
        version = metadata.get("version", "")
        if version and not re.match(r"^\d+\.\d+\.\d+", str(version)):
            issues.append({
                "severity": "WARN",
                "type": "metadata",
                "message": f"Versie '{version}' lijkt geen semver formaat (x.y.z)",
            })

    # ── Check 2: Required directories ─────────────────────────────
    for req_dir in REQUIRED_SKILL_DIRS:
        d = skill_path / req_dir
        if not d.exists():
            issues.append({
                "severity": "ERROR",
                "type": "structure",
                "message": f"Verplichte directory '{req_dir}/' ontbreekt",
                "fix": f"mkdir -p {d}",
            })
        elif not d.is_dir():
            issues.append({
                "severity": "ERROR",
                "type": "structure",
                "message": f"'{req_dir}' bestaat maar is geen directory",
            })

    # ── Check 3: Command files ────────────────────────────────────
    commands_dir = skill_path / "commands"
    if commands_dir.exists() and commands_dir.is_dir():
        cmd_files = [f for f in commands_dir.iterdir()
                     if f.is_file() and f.suffix.lower() in COMMAND_EXTENSIONS]
        if not cmd_files:
            issues.append({
                "severity": "WARN",
                "type": "commands",
                "message": f"Geen command bestanden (*.py, *.sh, *.js, etc.) in commands/",
            })
        else:
            for cmd_file in cmd_files:
                if cmd_file.stat().st_size == 0:
                    issues.append({
                        "severity": "WARN",
                        "type": "commands",
                        "message": f"Command bestand is leeg: commands/{cmd_file.name}",
                    })
                # Check shebang for script files
                if cmd_file.suffix in {".sh", ".py", ".js", ".lua"}:
                    content = cmd_file.read_text(encoding="utf-8", errors="replace")
                    if not content.startswith("#!"):
                        issues.append({
                            "severity": "INFO",
                            "type": "commands",
                            "message": f"Command '{cmd_file.name}' mist shebang (#!) regel",
                        })
    else:
        if not any(i["type"] == "structure" and "commands" in i["message"] for i in issues):
            issues.append({
                "severity": "ERROR",
                "type": "commands",
                "message": "commands/ directory ontbreekt of is ongeldig",
            })

    # ── Check 4: Prompt files ─────────────────────────────────────
    prompts_dir = skill_path / "prompts"
    if prompts_dir.exists() and prompts_dir.is_dir():
        prompt_files = [f for f in prompts_dir.iterdir() if f.is_file()]
        if not prompt_files:
            issues.append({
                "severity": "INFO",
                "type": "prompts",
                "message": f"Geen prompt bestanden in prompts/",
            })
        else:
            for pf in prompt_files:
                if pf.stat().st_size == 0:
                    issues.append({
                        "severity": "WARN",
                        "type": "prompts",
                        "message": f"Prompt bestand is leeg: prompts/{pf.name}",
                    })
    else:
        issues.append({
            "severity": "WARN",
            "type": "prompts",
            "message": "prompts/ directory ontbreekt (optioneel maar aanbevolen)",
        })

    # ── Check 5: Permissions ──────────────────────────────────────
    if metadata:
        permissions = metadata.get("permissions", {})
        if isinstance(permissions, dict):
            read_only = permissions.get("read_only", None)
            needs_approval = permissions.get("needs_approval", None)

            if read_only is None and needs_approval is None:
                issues.append({
                    "severity": "INFO",
                    "type": "permissions",
                    "message": ("Geen permissions gespecificeerd in metadata (read_only,"
                           "needs_approval)"),
                })

            # Check file permissions on command files
            if commands_dir.exists():
                for cmd_file in commands_dir.iterdir():
                    if cmd_file.is_file():
                        try:
                            fmode = cmd_file.stat().st_mode
                            is_exec = bool(fmode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
                            if not is_exec and cmd_file.suffix in {".sh", ".py", ".js"}:
                                issues.append({
                                    "severity": "WARN",
                                    "type": "permissions",
                                    "message": f"Command '{cmd_file.name}' heeft geen execute permissie",
                                    "fix": f"chmod +x {cmd_file}",
                                })
                        except OSError:
                            pass

    # ── Check 6: Tool dependencies ────────────────────────────────
    if metadata:
        tool_deps = metadata.get("tool_dependencies", [])
        if isinstance(tool_deps, list) and tool_deps:
            toolcase_dir = Path(__file__).parent.resolve()
            for dep in tool_deps:
                dep_path = toolcase_dir / dep
                # Check in PATH as well
                dep_in_path = shutil.which(dep) is not None
                dep_in_toolcase = dep_path.exists()

                if dep_in_toolcase:
                    continue
                if dep in TOOLCASE_TOOLS:
                    issues.append({
                        "severity": "WARN",
                        "type": "dependencies",
                        "message": f"Tool dependency '{dep}' is een ToolCase tool maar niet gevonden in {toolcase_dir}",
                    })
                elif not dep_in_path:
                    issues.append({
                        "severity": "ERROR",
                        "type": "dependencies",
                        "message": f"Tool dependency '{dep}' is niet geïnstalleerd (niet in PATH of ToolCase)",
                    })
        elif isinstance(tool_deps, list) and not tool_deps:
            issues.append({
                "severity": "INFO",
                "type": "dependencies",
                "message": "Geen tool_dependencies gespecificeerd (optioneel)",
            })

    # ── Check 7: Test command ─────────────────────────────────────
    if metadata:
        test_cmd = metadata.get("test_command") or metadata.get("test")
        if test_cmd:
            # Test command is specified — check if the referenced script exists
            test_parts = str(test_cmd).split()
            if test_parts:
                test_target = test_parts[0]
                test_path = skill_path / test_target
                if not test_path.exists():
                    test_in_path = shutil.which(test_target)
                    if not test_in_path:
                        issues.append({
                            "severity": "WARN",
                            "type": "tests",
                            "message": f"Test command '{test_target}' niet gevonden ({test_target} bestaat niet in skill of PATH)",
                        })
        else:
            issues.append({
                "severity": "INFO",
                "type": "tests",
                "message": "Geen test_command in metadata (optioneel maar aanbevolen)",
            })

    # ── Check 8: Registry registration ────────────────────────────
    if metadata:
        skill_name = metadata.get("name", skill_path.name)
        registry = _find_registry()
        if registry:
            skill_reg_path = registry / skill_path.name
            if not skill_reg_path.exists() and not any(
                skill_path.samefile(p) for p in registry.iterdir() if p.is_dir()
            ):
                issues.append({
                    "severity": "INFO",
                    "type": "registry",
                    "message": f"Skill '{skill_name}' is niet geregistreerd in skill registry ({registry})",
                    "fix": f"python skill_installer.py install {skill_path}",
                })
        else:
            issues.append({
                "severity": "INFO",
                "type": "registry",
                "message": "Geen skill registry gevonden. Skills worden alleen lokaal gevalideerd.",
            })

    return issues


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------


def install_skill(source: str, force: bool = False,
                  trust_executables: bool = False) -> dict[str, Any]:
    """
    Install a skill from a source path or name.

    Security: symlinks are rejected by default (use --force to allow).
    Executable commands require explicit --trust-executables.

    Returns a dict with result information.
    """
    result: dict[str, Any] = {
        "action": "install",
        "source": source,
        "success": False,
        "messages": [],
        "warnings": [],
    }

    # Resolve source path
    src_path = Path(source).resolve()

    # If source doesn't exist as path, check if it's a known skill name
    if not src_path.exists():
        # Check if it's an installed skill name
        installed = _find_installed_skills()
        if source in installed:
            result["messages"].append(f"Skill '{source}' is al geïnstalleerd op {installed[source]}")
            result["success"] = True
            result["path"] = str(installed[source])
            return result

        # Check ToolCase tools config for known skills
        toolcase_dir = Path(__file__).parent.resolve()
        config_path = toolcase_dir / "tools_config.json"
        if config_path.exists():
            config = _load_json(config_path)
            if config and isinstance(config, dict):
                for tool in config.get("tools", []):
                    if isinstance(tool, dict) and tool.get("name", "").replace(".py", "") == source:
                        result["messages"].append(
                            f"'{source}' is een ToolCase tool, geen skill package. Gebruik: python improve.py --{source.replace('_', '-')}"
                        )
                        result["warnings"].append("ToolCase tools worden niet via de skill installer beheerd")
                        return result

        result["messages"].append(f"❌ Skill niet gevonden: '{source}' bestaat niet als pad of geïnstalleerde skill")
        return result

    if not src_path.is_dir():
        result["messages"].append(f"❌ '{source}' is geen directory")
        return result

    # Validate first
    issues = validate_skill(src_path)
    errors = [i for i in issues if i["severity"] == "ERROR"]
    if errors and not force:
        result["messages"].append(f"❌ Validatie gefaald: {len(errors)} fout(en)")
        for e in errors:
            result["messages"].append(f"   ERROR: {e['message']}")
        result["issues"] = issues
        return result

    # Load metadata
    metadata = _load_metadata(src_path)
    if not metadata:
        result["messages"].append("❌ Kan metadata niet laden — installatie afgebroken")
        return result

    skill_name = metadata.get("name", src_path.name)

    # Install: copy/link to registry
    registry = _ensure_registry()
    target_dir = registry / skill_name

    if target_dir.exists():
        if force:
            shutil.rmtree(target_dir)
            result["messages"].append(f"🔄 Bestaande skill '{skill_name}' overschreven")
        else:
            result["messages"].append(f"⚠ Skill '{skill_name}' bestaat al in registry. Gebruik --force om te overschrijven.")
            result["path"] = str(target_dir)
            result["success"] = True
            return result

    # Security: scan for symlinks in source before copying
    symlinks_found: list[str] = []
    for root, dirs, files in os.walk(src_path):
        # Check directory symlinks
        for d in dirs:
            full = Path(root) / d
            if full.is_symlink():
                symlinks_found.append(str(full))
        # Check file symlinks
        for f in files:
            full = Path(root) / f
            if full.is_symlink():
                symlinks_found.append(str(full))

    if symlinks_found:
        symlink_list = "\n    ".join(symlinks_found[:10])
        msg = (f"⚠ Security: {len(symlinks_found)} symlink(s) gevonden in "
               f"skill package. Symlinks kunnen buiten de target directory wijzen "
               f"en zijn een supply-chain risico.\n  Symlinks:\n    {symlink_list}")
        if force:
            result["warnings"].append(msg)
            result["warnings"].append(
                "Symlinks worden toch gekopieerd vanwege --force. "
                "Controleer handmatig of alle symlink-targets binnen de skill registry blijven.")
        else:
            result["messages"].append(
                f"❌ {msg}\n  Gebruik --force om symlinks toch toe te staan "
                f"(niet aanbevolen voor untrusted packages).")
            result["success"] = False
            return result

    # Copy skill directory (with symlinks dereferenced for safety)
    try:
        if force:
            # Force mode: copy with symlinks preserved (user accepts risk)
            shutil.copytree(
                src_path,
                target_dir,
                ignore=shutil.ignore_patterns("__pycache__", ".git", "node_modules"),
                symlinks=True,
            )
        else:
            # Safe mode: dereference symlinks (copy actual content instead of links)
            def _safe_copy(src: str, dst: str, *, follow_symlinks: bool = True):
                """Copy function that dereferences symlinks for safety."""
                return shutil.copy2(src, dst, follow_symlinks=follow_symlinks)

            shutil.copytree(
                src_path,
                target_dir,
                ignore=shutil.ignore_patterns("__pycache__", ".git", "node_modules"),
                symlinks=False,  # Never follow symlinks — copy the content instead
                copy_function=_safe_copy,
            )
    except OSError as e:
        result["messages"].append(f"❌ Kopieer fout: {e}")
        return result

    # Security: verify no paths resolve outside the target directory
    _verify_containment(target_dir, result)

    # Update registry index with source origin and trust status
    index = _read_registry_index()
    index[skill_name] = {
        "name": skill_name,
        "path": str(target_dir.resolve()),
        "version": str(metadata.get("version", "0.0.0")),
        "description": str(metadata.get("description", "")),
        "installed_at": datetime.now().isoformat(),
        "source": str(src_path.resolve()),
        "source_type": "local" if src_path.is_relative_to(Path.home()) else "external",
        "executables_trusted": trust_executables,
        "symlinks_were_present": len(symlinks_found) > 0,
    }
    _write_registry_index(index)

    result["success"] = True
    result["path"] = str(target_dir.resolve())
    result["messages"].append(f"✅ Skill '{skill_name}' geïnstalleerd naar {target_dir}")
    if errors:
        result["warnings"].append(f"Geïnstalleerd met {len(errors)} validatiefout(en) — gebruik --force om te negeren")
    else:
        result["messages"].append("✅ Validatie: geslaagd")

    # Make command files executable ONLY if explicitly trusted
    commands_dir = target_dir / "commands"
    if commands_dir.exists():
        for cmd_file in commands_dir.iterdir():
            if cmd_file.is_file() and cmd_file.suffix in {".sh", ".py", ".js"}:
                if trust_executables:
                    try:
                        current = cmd_file.stat().st_mode
                        cmd_file.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    except OSError:
                        pass
                else:
                    result["warnings"].append(
                        f"Command '{cmd_file.name}' is NIET uitvoerbaar gemaakt. "
                        f"Gebruik --trust-executables om dit toe te staan.")

    if not trust_executables and commands_dir.exists():
        cmd_count = len([f for f in commands_dir.iterdir()
                        if f.is_file() and f.suffix in {".sh", ".py", ".js"}])
        if cmd_count > 0:
            result["messages"].append(
                f"ℹ {cmd_count} command bestand(en) niet uitvoerbaar. "
                f"Gebruik --trust-executables om uitvoerbaar te maken.")

    return result


def _verify_containment(target_dir: Path, result: dict[str, Any]) -> None:
    """Verify all files in target_dir resolve within target_dir (no symlink escapes)."""
    issues: list[str] = []
    for root, dirs, files in os.walk(target_dir):
        for name in dirs + files:
            full = Path(root) / name
            try:
                resolved = full.resolve()
                if not str(resolved).startswith(str(target_dir.resolve())):
                    issues.append(
                        f"⚠ Path containment violation: {full} → {resolved}")
            except OSError:
                issues.append(f"⚠ Cannot resolve path: {full}")

    if issues:
        for issue in issues[:5]:
            result["warnings"].append(issue)
        if len(issues) > 5:
            result["warnings"].append(f"... en nog {len(issues) - 5} containment issues")
        result["warnings"].append(
            "Path containment check gefaald. Deze skill kan toegang hebben "
            "tot bestanden buiten zijn eigen directory.")


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_skill(name: str) -> dict[str, Any]:
    """
    Run tests for an installed skill.

    Returns a dict with results.
    """
    result: dict[str, Any] = {
        "action": "test",
        "skill": name,
        "success": False,
        "output": [],
        "errors": [],
    }

    installed = _find_installed_skills()
    if name not in installed:
        result["errors"].append(f"❌ Skill '{name}' is niet geïnstalleerd")
        return result

    skill_path = installed[name]
    metadata = _load_metadata(skill_path)

    if not metadata:
        result["errors"].append(f"❌ Kan metadata niet laden voor skill '{name}'")
        return result

    test_cmd = metadata.get("test_command") or metadata.get("test")
    if not test_cmd:
        result["output"].append(f"ℹ Skill '{name}' heeft geen test_command in metadata")
        result["success"] = True  # Nothing to run is not a failure
        return result

    # Resolve and run test command
    test_cmd_str = str(test_cmd)

    # If the test command references a local file, resolve relative to skill path
    test_parts = test_cmd_str.split()
    test_exe = test_parts[0]
    test_path = skill_path / test_exe

    if test_path.exists():
        # Use the full path
        test_parts[0] = str(test_path.resolve())
    else:
        # Check PATH
        which_test = shutil.which(test_exe)
        if which_test:
            test_parts[0] = which_test
        else:
            result["errors"].append(f"❌ Test executable '{test_exe}' niet gevonden")
            return result

    try:
        proc = subprocess.run(
            test_parts,
            cwd=str(skill_path),
            capture_output=True,
            text=True,
            timeout=120,
        )
        result["exit_code"] = proc.returncode
        if proc.stdout:
            result["output"].extend(proc.stdout.splitlines())
        if proc.stderr:
            result["errors"].extend(proc.stderr.splitlines())

        if proc.returncode == 0:
            result["success"] = True
        else:
            result["errors"].insert(0, f"❌ Test gefaald met exit code {proc.returncode}")

    except FileNotFoundError:
        result["errors"].append(f"❌ Kan test command niet uitvoeren: {test_cmd_str}")
    except subprocess.TimeoutExpired:
        result["errors"].append("❌ Test timeout (120s)")
    except OSError as e:
        result["errors"].append(f"❌ Test fout: {e}")

    return result


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def list_skills(json_output: bool = False) -> dict[str, Any]:
    """
    List all installed skills with their metadata.
    """
    installed = _find_installed_skills()
    registry = _find_registry()
    index = _read_registry_index()

    skills_data: dict[str, dict[str, Any]] = {}
    for name, path in sorted(installed.items()):
        metadata = _load_metadata(path)
        reg_info = index.get(name, {})

        skills_data[name] = {
            "name": name,
            "path": str(path.resolve()),
            "version": str(metadata.get("version", reg_info.get("version", "?"))) if metadata else "?",
            "description": str(metadata.get("description", reg_info.get("description", ""))) if metadata else "",
            "commands_count": len(list((path / "commands").iterdir())) if (path / "commands").exists() else 0,
            "prompts_count": len(list((path / "prompts").iterdir())) if (path / "prompts").exists() else 0,
            "installed_at": reg_info.get("installed_at", ""),
            "has_metadata": metadata is not None,
            "has_tests": bool(metadata.get("test_command") or metadata.get("test")) if metadata else False,
        }

    result = {
        "action": "list",
        "registry_path": str(registry) if registry else "N/A",
        "count": len(skills_data),
        "skills": skills_data,
    }

    return result


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def print_validation_report(issues: list[dict]) -> None:
    """Print a formatted validation report."""
    if not issues:
        print("\n ✅ Skill validatie: GEEN PROBLEMEN")
        print("=" * 60)
        return

    by_severity = defaultdict(list)
    for issue in issues:
        by_severity[issue["severity"]].append(issue)

    errors = by_severity.get("ERROR", [])
    warnings = by_severity.get("WARN", [])
    infos = by_severity.get("INFO", [])

    print(f"\n{'=' * 60}")
    print(f" 🔍 SKILL VALIDATIE — {len(issues)} bevinding(en)")
    print(f"{'=' * 60}")
    print(f"   ❌ Errors:   {len(errors)}")
    print(f"   ⚠  Warnings: {len(warnings)}")
    print(f"   💡 Info:     {len(infos)}")
    print()

    type_names = {
        "exists": "Bestaat",
        "metadata": "Metadata",
        "structure": "Directory Structuur",
        "commands": "Command Bestanden",
        "prompts": "Prompt Bestanden",
        "permissions": "Permissies",
        "dependencies": "Tool Dependencies",
        "tests": "Tests",
        "registry": "Registry",
    }

    # Group by type within each severity
    for severity, icon in [("ERROR", "❌"), ("WARN", "⚠"), ("INFO", "💡")]:
        sev_issues = by_severity.get(severity, [])
        if not sev_issues:
            continue
        by_type: dict[str, list[dict]] = defaultdict(list)
        for issue in sev_issues:
            by_type[issue["type"]].append(issue)

        for type_key, type_issues in sorted(by_type.items()):
            type_name = type_names.get(type_key, type_key)
            print(f" ── {type_name} ({len(type_issues)}) ──")
            for issue in type_issues:
                print(f"   {icon} {issue['message']}")
                if issue.get("fix"):
                    print(f"      🔧 {issue['fix']}")
        print()

    if not errors:
        print(" ✅ Geen errors — skill is valideerbaar\n")


def print_list(result: dict[str, Any]) -> None:
    """Print formatted skill list."""
    count = result["count"]
    registry = result.get("registry_path", "N/A")
    skills = result.get("skills", {})

    print(f"\n{'=' * 60}")
    print(f" 📋 GEÏNSTALLEERDE SKILLS ({count})")
    print(f"{'=' * 60}")
    print(f" Registry: {registry}")
    print()

    if not skills:
        print("   (geen skills geïnstalleerd)")
        print()
        return

    for name, info in sorted(skills.items()):
        meta_icon = "✅" if info["has_metadata"] else "⚠"
        test_icon = "🧪" if info["has_tests"] else "  "
        print(f"   {meta_icon} {test_icon}  {name:<25s} v{info['version']:<10s}")
        print(f"       📁 {info['path']}")
        if info["description"]:
            wrapped = textwrap.fill(info["description"], width=70, initial_indent="       ", subsequent_indent="       ")
            print(wrapped)
        print(f"       📄 {info['commands_count']} commands, {info['prompts_count']} prompts")
        if info["installed_at"]:
            print(f"       🕐 Geïnstalleerd: {info['installed_at']}")
        print()

    print(f"{'=' * 60}\n")


def print_install_result(result: dict[str, Any]) -> None:
    """Print formatted install result."""
    print(f"\n{'=' * 60}")
    print(f" 🧩 SKILL INSTALLER")
    print(f"{'=' * 60}")
    print(f" Actie:    install")
    print(f" Source:   {result['source']}")
    print()

    for msg in result.get("messages", []):
        print(f"   {msg}")

    for warn in result.get("warnings", []):
        print(f"   ⚠ {warn}")

    if result.get("path"):
        print(f"\n   📁 Pad: {result['path']}")

    if result.get("issues"):
        errors = [i for i in result["issues"] if i["severity"] == "ERROR"]
        if errors:
            print(f"\n   ❌ Validatie errors ({len(errors)}):")
            for e in errors:
                print(f"      - {e['message']}")

    print(f"\n   Status: {'✅ GELUKT' if result['success'] else '❌ MISLUKT'}")
    print(f"{'=' * 60}\n")


def print_test_result(result: dict[str, Any]) -> None:
    """Print formatted test result."""
    skill = result.get("skill", "?")
    print(f"\n{'=' * 60}")
    print(f" 🧪 SKILL TEST — {skill}")
    print(f"{'=' * 60}")

    for line in result.get("output", []):
        print(f"   {line}")

    for err in result.get("errors", []):
        print(f"   {err}")

    print(f"\n   Status: {'✅ GESLAAGD' if result['success'] else '❌ GEFAALD'}")
    print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Skill installer main entry point."""
    parser = argparse.ArgumentParser(
        description="skill_installer.py — Installeert en valideert Hermes/Sabine skills",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Voorbeelden:
              python skill_installer.py validate ./my-skill
              python skill_installer.py validate ./my-skill --fix
              python skill_installer.py install ./my-skill
              python skill_installer.py install ./my-skill --force
              python skill_installer.py install my-skill-name
              python skill_installer.py test my-skill-name
              python skill_installer.py list
              python skill_installer.py list --json
        """),
    )

    subparsers = parser.add_subparsers(dest="command", help="Beschikbare commando's")

    # ── validate ──────────────────────────────────────────────────
    val_parser = subparsers.add_parser("validate", help="Valideer skill structuur")
    val_parser.add_argument("skill_path", help="Pad naar de skill directory")
    val_parser.add_argument("--fix", "-f", action="store_true", help="Probeer auto-fixes (indien van toepassing)")
    val_parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")

    # ── install ───────────────────────────────────────────────────
    inst_parser = subparsers.add_parser("install", help="Installeer een skill")
    inst_parser.add_argument("source", help="Skill naam of pad naar skill directory")
    inst_parser.add_argument("--force", "-f", action="store_true", help="Forceer installatie (overschrijf bestaand, negeer fouten, sta symlinks toe)")
    inst_parser.add_argument("--trust-executables", action="store_true", help="Maak command bestanden uitvoerbaar (alleen voor vertrouwde skill packages)")
    inst_parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")

    # ── test ──────────────────────────────────────────────────────
    test_parser = subparsers.add_parser("test", help="Run skill tests")
    test_parser.add_argument("skill_name", help="Naam van de geïnstalleerde skill")
    test_parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")

    # ── list ──────────────────────────────────────────────────────
    list_parser = subparsers.add_parser("list", help="Toon geïnstalleerde skills")
    list_parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")

    # ── Global ────────────────────────────────────────────────────
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON (global, voor subcommands)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(EXIT_USAGE)

    # Determine JSON mode (from subparser or global flag)
    use_json = getattr(args, "json", False) or args.json

    # ── Handle validate ───────────────────────────────────────────
    if args.command == "validate":
        skill_path = Path(args.skill_path).resolve()
        if not skill_path.exists():
            msg = f"❌ Pad bestaat niet: {args.skill_path}"
            if use_json:
                _print_json({"error": msg, "issues": []})
            else:
                print(f"\n {msg}")
            sys.exit(EXIT_ERROR)

        issues = validate_skill(skill_path, fix=args.fix)

        if use_json:
            _print_json({
                "skill_path": str(skill_path),
                "total": len(issues),
                "errors": len([i for i in issues if i["severity"] == "ERROR"]),
                "warnings": len([i for i in issues if i["severity"] == "WARN"]),
                "infos": len([i for i in issues if i["severity"] == "INFO"]),
                "issues": issues,
            })
        else:
            print_validation_report(issues)

        has_errors = any(i["severity"] == "ERROR" for i in issues)
        sys.exit(EXIT_ERROR if has_errors else EXIT_OK)

    # ── Handle install ────────────────────────────────────────────
    elif args.command == "install":
        trust_exec = getattr(args, "trust_executables", False)
        result = install_skill(args.source, force=args.force,
                               trust_executables=trust_exec)

        if use_json:
            _print_json(result)
        else:
            print_install_result(result)

        sys.exit(EXIT_OK if result["success"] else EXIT_ERROR)

    # ── Handle test ───────────────────────────────────────────────
    elif args.command == "test":
        result = test_skill(args.skill_name)

        if use_json:
            _print_json(result)
        else:
            print_test_result(result)

        sys.exit(EXIT_OK if result["success"] else EXIT_ERROR)

    # ── Handle list ───────────────────────────────────────────────
    elif args.command == "list":
        result = list_skills(json_output=use_json)

        if use_json:
            _print_json(result)
        else:
            print_list(result)

        sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()