# ToolCase v5.5.0 — Release Procedure

## Prerequisites

- All changes committed and pushed to `master`
- CI green on all platforms (Ubuntu + Windows, Python 3.11–3.13)

## Release Steps

### 1. Pre-tag verification

```bash
# Run all checks except the git tag check (tag doesn't exist yet)
python release_readiness.py --pre-tag
# Must show: GO ✅
# Required checks: ALL PASSED
# Clean working tree, CHANGELOG entry: required
```

### 2. Build and verify distributions

```bash
python -m build --sdist --wheel
python -m twine check dist/*
```

### 3. Install from wheel and smoke-test

```bash
# Create a clean temporary venv
python -m venv /tmp/tc_test

# Linux/Mac:
/tmp/tc_test/bin/pip install dist/toolcase-*.whl
/tmp/tc_test/bin/toolcase --version
/tmp/tc_test/bin/toolcase --verify-install
/tmp/tc_test/bin/pip check

# Windows (PowerShell):
.\test_venv\Scripts\Activate.ps1
pip install dist/toolcase-*.whl
toolcase --version
toolcase --verify-install
pip check
```

### 4. Tag and push

```bash
git tag -a v5.5.0 -m "ToolCase v5.5.0"
git push origin master
git push origin v5.5.0
```

### 5. Post-tag verification

```bash
# Now the tag exists — full verification
python release_readiness.py
# Must show: GO ✅ (including git tag check)
```

### 6. Create GitHub Release

- Go to https://github.com/SmokerGreenOG/ToolCase/releases
- Create release from tag `v5.5.0`
- Attach `dist/toolcase-5.5.0.tar.gz` and `dist/toolcase-5.5.0-py3-none-any.whl`
- Generate SHA-256 checksums:
  ```bash
  sha256sum dist/toolcase-5.5.0.tar.gz dist/toolcase-5.5.0-py3-none-any.whl
  ```

## Version Bump Checklist

After release, bump version in:
- `pyproject.toml` → `version = "5.5.0.dev0"`
- `manifest.json` → `"version": "5.5.0.dev0"`
- `tools_config.json` → `"__meta": {"version": "5.5.0.dev0"}`
- `improve.py` → `version="improve.py v5.5.0.dev0"`
- `README.md` → badge version
- `CHANGELOG.md` → add new version heading
- `SKILL.md` → version references
- `SECURITY.md` → supported version
