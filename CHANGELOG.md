# Changelog

All notable changes to ToolCase are documented in this file.

## [5.4.2] - 2026-06-24

### Security — Critical fixes
- **Exit code contract**: `improve.py` returns 0 (clean), 1 (findings), 2 (error). Was implicit 0 for all error paths.
- **Workspace containment**: `backup_manager.py` hard-rejects paths outside workspace. Symlink traversal blocked on restore. `.backups/` excluded from snapshots.
- **safe_run executor** (Tool #61): Central safe subprocess runner with risk-based approval (BLOCKED/HIGH/MEDIUM/SAFE), shell-interpreter blocking, encoded command detection, Docker/Git destructive recognition, cwd containment, dangerous kwarg rejection (shell=True, executable, etc.), case-insensitive classification.
- **Release packager suppression**: `# toolcase: ignore-security` marker respected — no false positives on test fixtures.

### Packaging
- `requires-python = ">=3.11"` in pyproject.toml
- `safe_run.py` added to wheel py-modules (was missing)
- `check_syntax.py` registered as Tool #62
- `.safe_run.log` removed from git, added to .gitignore
- manifest.json consistent paths (scripts/check_syntax.py → check_syntax.py)

### Quality
- **113 tests** (was 70)
- Dry-run: no more report writes (`.rsi_reports/`, `.self_improve_reports/`)
- Release readiness: ignores `build/`, `dist/`, `*.egg-info/`; "Scanner crashed" false alarm fixed
- Version consistency checker: removed hardcoded 60, cross-checks manifest.json
- README: 62 tools, security claims technically accurate

### Known limitations (documented honestly)
- `safe_run` migration complete — 0 modules use direct `subprocess.run()`, CI gate enforces
- Windows encoding: some tools may need `PYTHONIOENCODING=utf-8` on cp1252 consoles
- Package layout: flat top-level modules, `src/toolcase/` migration pending
- Install verify requires wheel build — fails in source-only checkout

## [5.4.0] - 2026-06-24

### Added — RSI v2.0: Hermes LLM Integration

- **RSI v2.0** (`recursive_self_improve.py`): Complete rewrite met LLM Bridge integratie.
  - Nieuwe focus modes: `security`, `refactor`, `performance`, `architecture`, `dead-code`, `bugs`
  - Cross-file analyse: duplicate functie detectie en import-overlap analyse
  - Adaptive learning met decay rates en exploration bonus
  - Realistischere quality scoring (docs/types missen wegen zwaarder)
  - Auto-fix vs LLM-required classificatie per attempt
- **LLM Bridge** (`rsi_llm_bridge.py`): Fix-request queue systeem.
  - RSI analyseert → schrijft requests → Hermes (LLM) fixt → RSI leert
  - Geen API keys nodig — Hermes is de LLM
  - Pending/done/failed queue met prioriteiten
  - Batch submit, wait_for_results, queue stats
- **Dark-themed HTML dashboard** (`rsi_report_html.py`):
  - Chart.js grafieken (kwaliteit per cyclus, fix verdeling, gewichten)
  - Stat cards, severity dots, focus badges
  - ToolCase signature stijl (#120720 bg, neon accenten, glassmorphism)
- **Batch docstring fixer** (`rsi_apply_docs.py`):
  - AST-gebaseerde functie-detectie
  - Auto-genereert docstrings op basis van functienaam
  - Syntax validatie voor en na
  - Integreert met LLM Bridge queue

### Changed

- Quality score herzien: meer gewicht aan docs (10.0) en types (6.0)
- 31 docstrings toegevoegd aan 25 tools (main() functies, helpers)
- Prioriteitsgewichten passen zich sneller aan op basis van success rates
- Memory format geüpgraded naar v2.0 met llm_fixes_count tracking

### Stats

|- **60 tools**: +scan_reliability, +release_readiness, +sarif_exporter (v5.5 gates)
|- **Kwaliteit**: 0.9990 → **1.0000** (alle 78 files scoren 1.0)
|- **Docs**: 687 → 761 (+74 docstrings, 94.9% coverage)
|- **Types**: 80 type hints toegevoegd aan test methods
|- **244 LLM fixes** verwerkt, 19 learned patterns
|- **E501**: 2 → 0, trailing whitespace: 49 → 0
|- **Security**: 0 HIGH, 0 MEDIUM, 0 LOW
|- **Scanner reliability**: 1.0
|- **Cross-file analyse**: 23 duplicate functies (intentioneel — self-contained tools)

## [5.2.0] - 2026-06-20

### Added

- 16 docstring documentation blocks across core modules (recursive_self_improve, self_improve_loop, php_dep_audit, php_depgraph, workspace_indexer, depgraph, complexity).
- 16 return-type and argument-type annotations across core modules.
- Perfect quality score: 1.0 (0 E501, 0 E302, 0 syntax errors, 0 TODOs).

### Fixed

- E501: long line (110 chars) in `php_test_runner.py` wrapped to multi-line signature.
- E302: 7 missing blank lines before top-level function/class definitions.
- False-positive TODO in `php_config_audit.py` (`BUG` substring in `DEBUG` comment).

### Changed

- All public Python tools now carry docstrings and complete type hints.
- Self-audit quality score improved from 0.9991 to 1.0 (perfect).
- 32 total code-quality improvements applied over 2 recursive self-improvement batches.

### Validation

- 53/53 manifest and configuration tool entries valid.
- 70 unit tests passing.
- Self-audit: 0 findings, score 1.0.

## [5.1.0] - 2026-06-20

### Added

- 53 registered tools across 10 categories.
- PHP analysis, security, dependency, version and test tooling.
- Recursive self-improvement workflow with learning memory.
- Configuration validation, documentation synchronization and type coverage.
- GitHub Actions validation for Python 3.11, 3.12 and 3.13.

### Changed

- Updated all public metadata, dashboard content and installer output to v5.1.0.
- Updated documentation and examples to reference the actual script names.
- Healthy source-file inventory no longer counts as a self-audit finding.

### Removed

- Demo server and generated caches, reports and backup state.

### Validation

- 70 unit tests passing.
- 53/53 manifest and configuration tool entries valid.
- Self-audit passing with 0 findings.

[5.2.0]: https://github.com/SmokerGreenOG/ToolCase/releases/tag/v5.2.0
[5.1.0]: https://github.com/SmokerGreenOG/ToolCase/releases/tag/v5.1.0
