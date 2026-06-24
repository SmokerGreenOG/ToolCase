---
name: toolcase-self-improve
description: "ToolCase v5.4.1 — 62 tools, RSI 2.0 met safe_run executor. Full autonomous code health workflow met dark-themed dashboard."
version: 5.4.1
author: SmokerGreenOG
metadata:
  hermes:
    tags: [toolcase, self-improvement, code-quality, automation, safety-first, code-audit, rsi, recursive]
---

# ToolCase v5.4 — Self-Improvement Skill

## Overview

ToolCase is a **62-tool code analysis and improvement toolkit**.
Use this skill when the user wants to **audit, improve, or self-heal** their codebase.

**🆕 RSI v2.0**: De recursive self-improvement is nu gekoppeld aan Hermes via een LLM Bridge — 
intelligente fixes (docs, types, refactors, security) zonder API keys. 
De RSI analyseert, Hermes fixt, de RSI leert.

**Key files:**
| File | Purpose |
|------|---------|
| `recursive_self_improve.py` | **RSI v2.0** — recursive self-improvement met LLM Bridge |
| `rsi_llm_bridge.py` | **LLM Bridge** — fix-request queue tussen RSI en Hermes |
| `rsi_report_html.py` | **Dashboard** — dark-themed HTML rapporten met Chart.js |
| `rsi_apply_docs.py` | **Batch fixer** — automatisch docstrings toevoegen via AST |
| `self_improve_loop.py` | 13-step autonomous improvement loop |
| `improve.py` | Main orchestrator — dispatches 62 registered tools |
| `i18n.py` | Translations (EN/NL/DE) |
| `tools_config.json` | Central config — 62 tools, 10 categories, 10 rules |
| `dashboard.html` | Web dashboard |
| `_protect.py` | Maker attribution verification (SHA256) |
| `manifest.json` | Hermes skill manifest |

---

## Quick Reference — When to use which tool

### 1. Code Analysis (syntax, lint, quality)

| If user says... | Use this tool | Example |
|----------------|---------------|---------|
| "Check syntax" | `improve.py` | `python improve.py <file>` |
| "Check all languages" | `multiscan.py` | `python multiscan.py <path>` |
| "How complex is this?" | `complexity.py` | `python complexity.py <file>` |
| "Show dependency graph" | `depgraph.py` | `python depgraph.py <path>` |
| "Preview before fixing" | `patch_preview.py` | `python patch_preview.py <file>` |

### 2. Bug & Dead Code Detection

| If user says... | Use this tool | Example |
|----------------|---------------|---------|
| "Find dead code" | `dead_code_finder.py` | `python dead_code_finder.py <path>` |
| "Find TODO/FIXME" | `todo_tracker.py` | `python todo_tracker.py <path>` |
| "Analyze state usage" | `state_inspector.py` | `python state_inspector.py <path>` |
| "Detect fake/demo UI" | `fake_ui_detector.py` | `python fake_ui_detector.py <path>` |
| "Find buttons without action" | `button_action_scanner.py` | `python button_action_scanner.py <path>` |

### 3. Security

| If user says... | Use this tool | Example |
|----------------|---------------|---------|
| "Scan for secrets" | `security_scan.py` | `python security_scan.py <path>` |
| "Check .env" | `env_check.py` | `python env_check.py check <path>` |
| "Audit dependencies" | `dependency_audit.py` | `python dependency_audit.py <path>` |
| "Check PHP security" | `php_checker.py` | `python php_checker.py <path> -r` |
| "Check PHP complexity" | `php_complexity.py` | `python php_complexity.py <path> -r` |
| "Show PHP dependencies" | `php_depgraph.py` | `python php_depgraph.py <path> -r` |
| "Find PHP dead code" | `php_dead_code.py` | `python php_dead_code.py <path> -r` |
| "Audit PHP config" | `php_config_audit.py` | `python php_config_audit.py <path>` |
| "Check PHP version compat" | `php_version_audit.py` | `python php_version_audit.py <path> --target 8.1` |
| "Run PHP tests" | `php_test_runner.py` | `python php_test_runner.py <path>` |
| "Audit Composer deps" | `php_dep_audit.py` | `python php_dep_audit.py <path>` |

### 4. Project Health

| If user says... | Use this tool | Example |
|----------------|---------------|---------|
| "Check project structure" | `project_doctor.py` | `python project_doctor.py <path>` |
| "Index workspace" | `workspace_indexer.py` | `python workspace_indexer.py <path>` |
| "Run tests" | `test_runner.py` | `python test_runner.py <path>` |
| "Check docs vs code" | `docs_sync.py` | `python docs_sync.py <path>` |
| "Check config state" | `agent_memory.py` | `python agent_memory.py <path>` |

### 5. Frontend / Backend

| If user says... | Use this tool | Example |
|----------------|---------------|---------|
| "Scan routes" | `route_scanner.py` | `python route_scanner.py <path>` |
| "Link frontend-backend" | `frontend_backend_linker.py` | `python frontend_backend_linker.py <path>` |
| "Check UI consistency" | `ui_consistency.py` | `python ui_consistency.py <path>` |
| "Find feature gaps" | `feature_gap_analyzer.py` | `python feature_gap_analyzer.py <path>` |
| "Check API contracts" | `api_contract_checker.py` | `python api_contract_checker.py <path>` |

### 6. Safety — Guards (ALWAYS use these first for dangerous operations)

| If user says... | Use this tool | Example |
|----------------|---------------|---------|
| "Is this command safe?" | `command_guard.py` | `python command_guard.py "rm -rf /"` |
| "Is this file protected?" | `file_guard.py` | `python file_guard.py check .env` |
| "What can the agent do?" | `permission_audit.py` | `python permission_audit.py` |

### 7. Build & Debug

| If user says... | Use this tool | Example |
|----------------|---------------|---------|
| "Build failed" | `build_doctor.py` | `python build_doctor.py <path>` |
| "View logs" | `log_viewer.py` | `python log_viewer.py <path>` |
| "Explain this error" | `error_explainer.py` | `python error_explainer.py "ModuleNotFoundError"` |
| "Make a release" | `release_packager.py` | `python release_packager.py <path>` |
| "Generate changelog" | `changelog_generator.py` | `python changelog_generator.py --git-log HEAD~10..HEAD` |

### 8. Lifecycle

| If user says... | Use this tool | Example |
|----------------|---------------|---------|
| "Backup this file" | `backup_manager.py` | `python backup_manager.py snapshot <path>` |
| "Roll back" | `rollback.py` | `python rollback.py restore <backup>` |
| "Install a skill" | `skill_installer.py` | `python skill_installer.py install <name>` |
| "Self-improve" | `self_improve_loop.py` | **See below** |

---

## The `self_improve_loop.py` — 13-Step Autonomous Workflow

This is the crown jewel — an autonomous loop that coordinates the registered tool workflow.

### How to invoke

```bash
# Default: 1 cycle on ToolCase itself
python self_improve_loop.py

# 3 improvement cycles
python self_improve_loop.py --cycles 3

# Custom workspace
python self_improve_loop.py D:\\MyProject

# Analyse only — no changes
python self_improve_loop.py --dry-run

# Machine-readable output
python self_improve_loop.py --json
```

### The 13 Steps

```
┌─────────────────────────────────────────────┐
│  Step  1: Scan workspace (.py files)        │
│  Step  2: Analyze code quality              │
│  Step  3: Find bugs, TODOs, dead code       │
│  Step  4: Check security                    │
│  Step  5: Check structure (docs, config)    │
│  Step  6: Make prioritized improvement plan │
│  Step  7: Show patch preview                │
│  Step  8: Create backup/snapshot            │
│  Step  9: Apply safe improvements           │
│  Step 10: Run tests / build checks          │
│  Step 11: Validate improvements work        │
│  Step 12: Generate full report              │
│  Step 13: Repeat max X cycles               │
└─────────────────────────────────────────────┘
```

### 10 Hard Safety Rules

These rules are **enforced in code** — never bypass them:

| # | Rule | Enforced by |
|---|------|-------------|
| 1 | **Backup before modify** | `SafetyManager.create_backup()` |
| 2 | **No secrets printed** | `SafetyManager` skips `.env` files |
| 3 | **No destructive commands** | Blocked before subprocess.run |
| 4 | **Workspace sandbox** | `Path.relative_to(workspace)` check |
| 5 | **Approval for delete** | `input()` prompt required |
| 6 | **file_guard for configs** | `SafetyManager.check_file_access()` |
| 7 | **command_guard for cmds** | `SafetyManager.check_command()` |
| 8 | **patch_preview before apply** | `step7_preview_patch()` called first |
| 9 | **Halt on regression** | Cycle stops if tests get worse |
| 10 | **Rollback on failure** | `SafetyManager.rollback()` restores .bak |

---

## Core Tool Reference

The tables below cover the original core workflow. The canonical complete
62-tool registry, including PHP, config and meta tooling, is maintained in
`manifest.json` and `tools_config.json`.

### Analyse & Code Quality (7)

| # | Tool | Script | Type | Risk | What it does |
|---|------|--------|------|------|-------------|
| 1 | **improve** | `improve.py` | Scan | Low | Python syntax + lint (long lines, trailing ws, TODO) |
| 2 | **multiscan** | `multiscan.py` | Scan | Low | Multi-language (.py/.ts/.tsx/.rs) |
| 3 | **complexity** | `complexity.py` | Analyze | Low | Cyclomatic complexity & cognitive load |
| 4 | **depgraph** | `depgraph.py` | Analyze | Low | Import/export dep graph + circular deps |
| 5 | **patch_preview** | `patch_preview.py` | Patch | Low | Diff preview before applying patches |
| 6 | **dead_code** | `dead_code_finder.py` | Analyze | Low | Unused imports, dead functions, commented-out code |
| 35 | **self_improve** | `self_improve_loop.py` | Workflow | Medium | 13-step autonomous self-improvement |

### Security & Environment (3)

| # | Tool | Script | Type | Risk | What it does |
|---|------|--------|------|------|-------------|
| 7 | **security_scan** | `security_scan.py` | Scan | Low | Secrets, API keys, eval/exec, SQL injection |
| 8 | **env_check** | `env_check.py` | Scan | Low | .env check, missing vars |
| 9 | **dependency_audit** | `dependency_audit.py` | Analyze | Low | Python/Node/Rust dep audit |

### Project Health (4)

| # | Tool | Script | Type | Risk | What it does |
|---|------|--------|------|------|-------------|
| 10 | **project_doctor** | `project_doctor.py` | Analyze | Low | Structure, init.py, naming |
| 11 | **workspace_index** | `workspace_indexer.py` | Index | Low | Index by language, dups |
| 12 | **test_runner** | `test_runner.py` | Execute | Medium | Discover + run tests (pytest, vitest, cargo) |
| 13 | **agent_memory** | `agent_memory.py` | Memory | Low | Hermes config state |

### Frontend & Backend (5)

| # | Tool | Script | Type | Risk | What it does |
|---|------|--------|------|------|-------------|
| 14 | **route_scanner** | `route_scanner.py` | Scan | Low | Frontend routes, orphaned pages |
| 15 | **fe_be_linker** | `frontend_backend_linker.py` | Analyze | Low | Cross-ref API endpoints |
| 16 | **ui_consistency** | `ui_consistency.py` | Analyze | Low | CSS vars vs hardcoded hex |
| 17 | **feature_gap** | `feature_gap_analyzer.py` | Analyze | Low | Missing error/loading states |
| 18 | **todo_tracker** | `todo_tracker.py` | Scan | Low | TODO/FIXME/HACK/XXX/BUG (comment-only) |

### Agent Safety (3) — ALWAYS USE BEFORE DANGEROUS OPERATIONS

| # | Tool | Script | Type | Risk | What it does |
|---|------|--------|------|------|-------------|
| 20 | **command_guard** | `command_guard.py` | Guard | Medium | Checks if a terminal command is safe |
| 21 | **file_guard** | `file_guard.py` | Guard | High | Protects .env, config from accidental write |
| 22 | **permission_audit** | `permission_audit.py` | Guard | Low | Agent permissions overview |

### Frontend QA (4)

| # | Tool | Script | Type | Risk | What it does |
|---|------|--------|------|------|-------------|
| 23 | **api_contract** | `api_contract_checker.py` | Analyze | Low | API contract mismatches |
| 24 | **fake_ui** | `fake_ui_detector.py` | Analyze | Low | Demo/fake UI detection |
| 25 | **button_scan** | `button_action_scanner.py` | Scan | Low | Buttons without real actions |
| 26 | **state_inspect** | `state_inspector.py` | Analyze | Low | React/Vue/Svelte state analysis |

### Build & Release (5)

| # | Tool | Script | Type | Risk | What it does |
|---|------|--------|------|------|-------------|
| 27 | **build_doctor** | `build_doctor.py` | Execute | Medium | Build diagnostics (npm, vite, tsc, Python) |
| 28 | **log_viewer** | `log_viewer.py` | Analyze | Low | Log scanner + error summary |
| 29 | **error_explainer** | `error_explainer.py` | Analyze | Low | Error → explanation + fix (30+ patterns) |
| 30 | **release_packager** | `release_packager.py` | Release | Medium | Preflight + build + zip + changelog |
| 31 | **changelog** | `changelog_generator.py` | Analyze | Low | CHANGELOG.md from git log |

### Lifecycle (4)

| # | Tool | Script | Type | Risk | What it does |
|---|------|--------|------|------|-------------|
| 19 | **rollback** | `rollback.py` | Restore | High | .bak backup restoration |
| 32 | **backup_manager** | `backup_manager.py` | Backup | High | Timestamped snapshots |
| 33 | **docs_sync** | `docs_sync.py` | Analyze | Low | README vs code cross-ref |
| 34 | **skill_installer** | `skill_installer.py` | Skill | Medium | Install + validate skills |

---

## Workflow — Full Code Audit

When the user asks for a complete code audit:

```bash
# Phase 1: Scan everything
python improve.py --all <path>                 # Full scan

# Phase 2: Deep dive
python complexity.py <path> --recursive        # Complexity hotspots
python dead_code_finder.py <path>              # Dead code
python security_scan.py <path>                 # Security audit
python todo_tracker.py <path>                  # Task-marker inventory
python project_doctor.py <path>                # Project health

# Phase 3: Self-improve
python self_improve_loop.py <path> --dry-run   # Analyse only
python self_improve_loop.py <path> --cycles 3  # Full auto-improve
```

---

## Workflow — Single Tool Usage (by category)

**When user says "check my Python code":**
1. `python improve.py <file>` — syntax + lint
2. `python complexity.py <file>` — complexity
3. `python dead_code_finder.py <file>` — dead code

**When user says "make it safe":**
1. `python security_scan.py <path>` — scan secrets
2. `python command_guard.py <cmd>` — check commands
3. `python file_guard.py check <path>` — protect configs

**When user says "check my frontend":**
1. `python route_scanner.py <path>` — scan routes
2. `python feature_gap_analyzer.py <path>` — find missing states
3. `python button_action_scanner.py <path>` — check interactivity
4. `python fake_ui_detector.py <path>` — detect mock UI

**When user says "build is broken":**
1. `python build_doctor.py <path>` — diagnose build
2. `python log_viewer.py <path>` — scan logs
3. `python error_explainer.py "<error>"` — explain error

**When user says "make a release":**
1. `python release_packager.py <path>` — package release
2. `python changelog_generator.py --git-log HEAD~10..HEAD` — changelog
3. `python backup_manager.py snapshot <path>` — snapshot

---

## Integration with Hermes

When Hermes needs to use ToolCase tools:

```python
from hermes_tools import terminal, read_file

# Run a tool
result = terminal("python improve.py target.py", timeout=30)
print(result['output'])
```

**Always wrap dangerous operations in guards:**
```python
# Step 1: Check command safety
guard = terminal("python command_guard.py 'rm -rf /' --json", timeout=10)

# Step 2: Preview patch
preview = terminal("python patch_preview.py target.py --json", timeout=10)

# Step 3: Create backup
backup = terminal("python backup_manager.py snapshot target.py", timeout=10)

# Step 4: Apply if all safe
if 'SAFE' in guard['output']:
    patch(path="target.py", old_string="...", new_string="...")
```

---

## Safety Checklist (for Hermes)

Before ANY modification, verify:
1. ✅ `command_guard.py` checked the command?
2. ✅ `file_guard.py` approved the file access?
3. ✅ `patch_preview.py` showed what changes?
4. ✅ `backup_manager.py` created a backup?
5. ✅ Test/build still pass after changes?
6. ✅ Rollback available if it fails?

---

## Manifest

See `manifest.json` for the machine-readable skill manifest.
