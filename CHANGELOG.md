# Changelog

All notable changes to ToolCase are documented in this file.

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
