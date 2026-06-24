# ⚡ ToolCase v5.4 — AI Agent Code Toolkit

[![Version](https://img.shields.io/badge/version-5.4.0-7C3AED?style=flat-square)](https://github.com/SmokerGreenOG/ToolCase/releases/tag/v5.4.0)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE)
[![Hermes](https://img.shields.io/badge/hermes--agent-ready-06b6d4?style=flat-square)]()
[![Tests](https://img.shields.io/badge/tests-70%2F70-success?style=flat-square)]()
[![Audit](https://img.shields.io/badge/self--audit-1.0000-brightgreen?style=flat-square)]()
[![CI](https://github.com/SmokerGreenOG/ToolCase/actions/workflows/ci.yml/badge.svg)](https://github.com/SmokerGreenOG/ToolCase/actions/workflows/ci.yml)
[![GitHub](https://img.shields.io/badge/github-SmokerGreenOG%2FToolCase-181717?style=flat-square&logo=github)]()

> **60 tools · 10 categories · 10 safety rules · RSI v2.0 LLM Bridge · reproducible self-audit**
> Built with ❤️ by [SmokerGreenOG](https://github.com/SmokerGreenOG)
> [![Repo](https://img.shields.io/badge/Repo-SmokerGreenOG%2FToolCase-7C3AED?style=flat-square)](https://github.com/SmokerGreenOG/ToolCase)

---

## 🛡️ Security

ToolCase ondergaat continue security-audits via de eigen toolchain. De codebase is
**vrij van kritieke kwetsbaarheden** — geen `eval()`, geen `shell=True`, geen
`os.system()` in productiecode.

| Check | Status |
|-------|--------|
| HIGH severity findings | **0** |
| MEDIUM severity findings | **1** (false positive — docsbeschrijving) |
| `eval()` / `exec()` in code | **0** |
| `shell=True` in subprocess | **0** |
| `os.system()` calls | **0** |
| License compliance | **61/61** |
| RSI quality score | **1.0000** |

**Actieve security-maatregelen:**
- **Subprocess safety**: Alle externe commando's gebruiken argument lists, nooit `shell=True`
- **Command guard** (`command_guard.py`): Blokkeert gevaarlijke commando's (`rm -rf`, `curl | sh`, etc.)
- **File guard** (`file_guard.py`): Beschermt configuratiebestanden tegen overschrijving
- **Skill installer hardening** (`skill_installer.py`): Symlink-bescherming, path containment verificatie, expliciete `--trust-executables` flag
- **AST-only syntax checks**: `check_syntax.py` schrijft geen `.pyc` bestanden — zero side-effects
- **Maker attribution**: Alle 61 tools geverifieerd via `__maker__` + SHA256 integriteit

> 💡 ToolCase is een **analyse-toolkit**, geen netwerkdienst. Het draait lokaal, maakt geen
> externe verbindingen, en voert alleen code uit die je zelf aanroept. De skill installer
> is de enige component die externe packages verwerkt — en die is expliciet gehard.

---

## 🚀 What is ToolCase?

**ToolCase** is a portable, production-ready code improvement toolkit designed for **AI agents** (Hermes, Claude Code, Codex) and **developers**.

It gives you **60 tools** across 10 categories — from static analysis and security scanning to build diagnostics, release packaging, **RSI v2.0 recursive self-improvement with LLM Bridge**, and AI prompt optimization.

**🆕 RSI v2.0**: Recursive Self-Improvement nu met Hermes LLM integratie — de RSI analyseert, Hermes fixt, de RSI leert. Geen API keys nodig.

**Zero external dependencies. Python 3.11+ only.** Runs on Windows, macOS, and Linux.

---

## 🖥️ Quick Start

```bash
# 1. Browse all 60 tools
python improve.py --list-tools

# 2. Full project audit (all tools)
python recursive_self_improve.py . --dry-run

# 3. Type coverage analysis
python type_coverage.py .

# 4. Security audit
python security_scan.py .

# 5. Project health check
python project_doctor.py .

# 6. Run all tests
python -m unittest discover -s tests

# 7. Full auto-improvement (5 cycles)
python recursive_self_improve.py . --cycles 5
```

---

## 📊 Dashboard

```
https://toolcase.nousresearch.com
```

Or run locally:
```bash
python -m http.server 8080 --directory .
# toolcase: ignore-security — expected local dashboard address.
# → http://localhost:8080/dashboard.html
```

---

## 📦 Installation

**Option A: Run the installer (Windows)**
```bash
.\install_toolcase.bat
```

**Option B: Manual install (any OS)**
```bash
mkdir -p ~/.hermes/skills/toolcase-self-improve
cp SKILL.md ~/.hermes/skills/toolcase-self-improve/
cp manifest.json ~/.hermes/skills/toolcase-self-improve/
hermes -s toolcase-self-improve
```

---

## 🔒 10 Safety Rules

| # | Rule |
|---|------|
| 1 | No destructive action without a backup |
| 2 | No terminal command without `command_guard.py` |
| 3 | No changes to .env, package.json, or config without `file_guard.py` |
| 4 | No patch without `patch_preview.py` first |
| 5 | No release if `security_scan.py` finds API keys |
| 6 | No release if `build_doctor.py` fails |
| 7 | No restore without explicit confirmation |
| 8 | No writing outside the workspace |
| 9 | No deletion without approval |
| 10 | No hidden changes — always show the diff |

---

## 🧰 Tool Reference — workflow highlights

ToolCase registers 60 unique tools. Tools can support multiple workflows, so a
tool may be relevant to more than one section below. The canonical complete
registry is maintained in `manifest.json` and `tools_config.json`.

### 🔍 Code Quality
| Tool | Description |
|------|-------------|
| `improve.py` | Main dispatcher — syntax, lint, and tool dispatch |
| `multiscan.py` | Multi-language scan (.py/.ts/.tsx/.rs) |
| `complexity.py` | Cyclomatic complexity & cognitive load |
| `depgraph.py` | Import/export dependency graph + circular deps |
| `patch_preview.py` | Diff preview before applying patches |
| `dead_code_finder.py` | Unused imports, dead functions, commented-out code |
| `self_improve_loop.py` | 13-step autonomous improvement loop |
| `code_churn_analyzer.py` | Hotspot detection — finds frequently-changed files |
| `performance_profiler.py` | Detects import-in-loop, open-in-loop patterns |

### 🔒 Security & Compliance
| Tool | Description |
|------|-------------|
| `security_scan.py` | Hardcoded API keys, eval/exec, SQL injection |
| `env_check.py` | .env validation, missing variables |
| `dependency_audit.py` | Python/Node/Rust dependency audit |
| `license_checker.py` | Verifies `__maker__` + `_protect` in all tools |
| `php_checker.py` | PHP code quality and security |

### 🐘 PHP Tools
| Tool | Description |
|------|-------------|
| `php_checker.py` | Code quality & security: syntax, SQL injection, XSS, file inclusion, secrets |
| `php_complexity.py` | Cyclomatic complexity & cognitive load per function |
| `php_depgraph.py` | Dependency graph: includes, namespaces, circular deps |
| `php_dead_code.py` | Dead code: unused functions, empty funcs, commented-out blocks |
| `php_config_audit.py` | Config audit: php.ini, .env, .htaccess, session security |
| `php_version_audit.py` | Version compatibility: deprecated/removed for PHP 5.x-8.x |
| `php_test_runner.py` | Test runner: PHPUnit/Pest discovery + execution |
| `php_dep_audit.py` | Composer audit: vulnerabilities, outdated packages, licenses |

### 🔍 APK Reverse Engineering
| Tool | Description |
|------|-------------|
| `apk_reverse.py` | Full APK decompilation (jadx → Java), manifest parsing, security scan, resource decoding, size optimization, signing verification, URL/string scan, APK comparison |

### 🩺 Project Health
| Tool | Description |
|------|-------------|
| `project_doctor.py` | Project structure, `__init__.py`, git status |
| `workspace_indexer.py` | Index by language, duplicates, ASCII tree |
| `test_runner.py` | Discover + run tests (pytest, vitest, cargo) |
| `agent_memory.py` | Hermes agent config state viewer |
| `type_coverage.py` | Type hint coverage measurement per file |

### 🌐 Frontend/Backend
| Tool | Description |
|------|-------------|
| `route_scanner.py` | Frontend routes, orphaned pages |
| `frontend_backend_linker.py` | Cross-reference API endpoints |
| `ui_consistency.py` | CSS vars vs hardcoded hex |
| `feature_gap_analyzer.py` | Missing error/loading states |
| `todo_tracker.py` | TODO/FIXME/HACK marker scanner |

### 🛡️ Agent Safety
| Tool | Description |
|------|-------------|
| `command_guard.py` | Terminal command safety checker |
| `file_guard.py` | Protects .env, config from overwrite |
| `permission_audit.py` | Agent permissions overview |

### 🎭 Frontend QA
| Tool | Description |
|------|-------------|
| `api_contract_checker.py` | Frontend-backend API contract mismatches |
| `fake_ui_detector.py` | Demo/fake UI detection |
| `button_action_scanner.py` | Buttons without real actions |
| `state_inspector.py` | React/Vue/Svelte state analysis |

### 🚀 Build & Release
| Tool | Description |
|------|-------------|
| `build_doctor.py` | Build diagnostics (npm, vite, tsc, Python) |
| `log_viewer.py` | Log scanner + error summary |
| `error_explainer.py` | Error → explanation + fix (30+ patterns) |
| `release_packager.py` | Preflight + build + zip + changelog |
| `changelog_generator.py` | CHANGELOG.md from git log |

### ♻️ Lifecycle
| Tool | Description |
|------|-------------|
| `backup_manager.py` | Timestamped snapshots + restore |
| `rollback.py` | .bak backup restoration |
| `docs_sync.py` | README vs code cross-reference |
| `skill_installer.py` | Hermes skill installer + validator |

### 📋 Config & Docs
| Tool | Description |
|------|-------------|
| `config_validator.py` | Validates tools_config.json ↔ manifest.json |
| `docs_sync_auto_fix.py` | Auto-updates README tool counts |
| `git_workflow_checker.py` | Conventional Commits + branch validation |

### 🤖 Meta & AI
| Tool | Description |
|------|-------------|
| `recursive_self_improve.py` | **RSI** — recursive self-improvement with memory |
| `rsi_llm_bridge.py` | RSI↔Hermes LLM bridge — fix-request queue zonder API keys |
| `rsi_report_html.py` | Dark-themed HTML dashboard met Chart.js grafieken |
| `rsi_apply_docs.py` | Batch docstring applicator via AST |
| `prompt_optimizer.py` | AI prompt analysis + optimization |
| `dependency_visualizer.py` | Mermaid.js dependency diagrams |
| `_protect.py` | Maker attribution integrity (SHA256) |

### 🔬 Quality Assurance
| Tool | Description |
|------|-------------|
| `scan_reliability.py` | Scanner reliability report — found/scanned/skipped/errors per scanner |
| `release_readiness.py` | Pre-release GO/NO-GO checklist — 10 checks before you ship |
| `sarif_exporter.py` | Export findings as SARIF v2.1.0 for GitHub Code Scanning |

---

## 🧪 Recursive Self-Improvement (RSI)

The crown jewel — `recursive_self_improve.py` learns from every cycle:

```
Analyze → Reflect → Generate → Evaluate → Learn → Repeat
```

```bash
# Quick scan (no changes)
python recursive_self_improve.py . --dry-run

# Full auto-improvement
python recursive_self_improve.py . --cycles 5

# Focus on code quality only
python recursive_self_improve.py . --focus code-quality
```

**Current self-audit status: 1.0000** (0 syntax errors, 0 E501, quality score 1.0000, 94.9% doc coverage)

---

## 📁 Project Structure

```
ToolCase v5.4/
├── improve.py                 # Main dispatcher
├── recursive_self_improve.py  # RSI — learns & improves itself
├── self_improve_loop.py       # 13-step improvement loop
├── tools_config.json          # Central JSON config
├── manifest.json              # Hermes skill manifest
├── SKILL.md                   # Hermes agent skill definition
├── dashboard.html             # Visual dashboard
├── i18n.py                    # EN/NL/DE translations
├── _protect.py                # Maker signature protection
├── install_toolcase.bat       # Windows installer
├── LICENSE                    # MIT
├── *.py                       # 60 registered tool scripts
├── scripts/
│   ├── check_syntax.py          # AST syntax checker
│   └── check_version_consistency.py  # CI version validator
├── tests/
│   ├── test_*.py              # 70 unit tests (8 modules)
│   └── __init__.py
└── README.md
```

---

## 📊 Metrics

| Metric | Value |
|--------|-------|
| Tools | 60 |
| Categories | 10 |
| Unit tests | 70/70 ✅ |
| Self-audit | Passing |
| Syntax errors | 0 |
| Security HIGH/MEDIUM | 1 (MEDIUM false positive) |
| Config/docs/security findings | 0 |
| License compliance | Passing |
| Python files | 78 |
| Lines of code | 34,700+ |
| RSI Quality | 1.0000 |
| E501 long lines | 0 |
| Security MEDIUM | 1 (false positive) |
| Doc coverage | 94.9% (761/803) |

---

## ⚙️ Requirements

- **Python 3.11+**
- That's it. Zero external dependencies.

---

## 📝 License

MIT License — see [LICENSE](LICENSE).

**Maker:** [SmokerGreenOG](https://github.com/SmokerGreenOG)
**Version:** 5.4.0
**Built for:** Hermes Agent · Claude Code · Codex · Every AI Agent

---

> ⚡ *"Your code's best friend — whether human or AI."*
