# Contributing to ToolCase

## Development requirements

- Python 3.11 or newer
- No mandatory third-party runtime dependencies

## Before submitting a pull request

Run:

```bash
python improve.py --verify-install
python -m unittest discover -s tests
python config_validator.py --json
python license_checker.py --json
python self_improve_loop.py . --dry-run --json --no-report
```

Requirements:

- All tests pass.
- The manifest and tools configuration remain synchronized.
- The self-audit reports zero actionable findings.
- Generated state, secrets and caches are not committed.
- User-facing changes are documented in `CHANGELOG.md`.

Use focused commits and explain the behavior change and validation performed.
