# Changelog

All notable changes to ToolCase are documented in this file.

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

- **57 tools** (was 54): +rsi_llm_bridge, +rsi_report_html, +rsi_apply_docs
- **Kwaliteit**: 0.9480 → 0.9582 na docstring batch
- **Docs**: 543 → 578 (+35 docstrings)
- **25 LLM fixes** verwerkt in eerste run
- **Cross-file analyse**: 22 duplicate functies gedetecteerd

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
