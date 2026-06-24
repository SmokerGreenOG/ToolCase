# ToolCase v5.4.1 — Release Procedure

## Prerequisites

- All changes committed and pushed to `master`
- CI green on all platforms (Ubuntu + Windows, Python 3.11–3.13)
- `release_readiness.py` returns GO ✅
- `python -m pytest tests/ -q` all pass

## Release Steps

### 1. Verify readiness

```bash
python release_readiness.py
# Must show: GO ✅
# Required checks: ALL PASSED
# Clean working tree, CHANGELOG entry, git tag all required
```

### 2. Build and verify distributions

```bash
python -m build --sdist --wheel
python -m twine check dist/*
```

### 3. Install from wheel and smoke-test

```bash
python -m venv /tmp/tc_test
# Linux/Mac:
/tmp/tc_test/bin/pip install dist/toolcase-*.whl
/tmp/tc_test/bin/toolcase --version
/tmp/tc_test/bin/toolcase --verify-install
# Windows:
# \tmp\tc_test\Scripts\pip install dist\toolcase-*.whl
# \tmp\tc_test\Scripts\toolcase --version
```

### 4. Tag and push

```bash
git tag -a v5.4.1 -m "ToolCase v5.4.1"
git push origin master
git push origin v5.4.1
```

### 5. Create GitHub Release

- Go to https://github.com/SmokerGreenOG/ToolCase/releases
- Create release from tag `v5.4.1`
- Title: "ToolCase v5.4.1"
- Copy relevant section from CHANGELOG.md as release notes
- Attach `dist/toolcase-5.4.1.tar.gz` and `dist/toolcase-5.4.1-py3-none-any.whl`
- Generate SHA-256 checksums:
  ```bash
  sha256sum dist/toolcase-5.4.1.tar.gz dist/toolcase-5.4.1-py3-none-any.whl
  ```

### 6. Update repo metadata

```bash
gh repo edit SmokerGreenOG/ToolCase --description "⚡ 62-tool AI agent code toolkit · RSI v2.0 · safe_run executor · Zero deps · Beta"
```

## Version Bump Checklist

After release, bump version in these files for the next dev cycle:
- `pyproject.toml` → `version = "5.5.0.dev0"`
- `manifest.json` → `"version": "5.5.0.dev0"`
- `tools_config.json` → `"__meta": {"version": "5.5.0.dev0"}`
- `improve.py` → `version="improve.py v5.5.0.dev0"`
- `README.md` → badge version
- `CHANGELOG.md` → add new version heading
- `SKILL.md` → version references
- `SECURITY.md` → supported version
