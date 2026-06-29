# Integration guide for ToolCase

## 1. Copy files

Copy this folder into your project:

```text
apk_reverse_suite/
```

## 2. Register with ToolCase 5.2

The pack-level `toolcase_registry_entry.json` contains three explicit values:

- append `manifest_entry` to ToolCase's `manifest.json` `tools` array;
- append `tools_config_entry` to ToolCase's `tools_config.json` `tools` array;
- append `category_update.append_tool` to the category identified by
  `category_update.category_id`.

If tool ID 54 is already in use, choose the same next free ID for both entries.
Validate the result with `python improve.py --verify-install`.

For a host that supports Python callable entry points directly, point it to
`apk_reverse_suite.toolcase_integration:run_toolcase_apk_reverse` instead.

## 3. Expected input

The integration function accepts either:

```python
run_toolcase_apk_reverse(apk_path="app.apk", output_dir="reports/app")
```

or a dict-like payload:

```python
run_toolcase_apk_reverse({
    "apk_path": "app.apk",
    "output_dir": "reports/app",
    "use_jadx": True,
    "use_apktool": True
})
```

## 4. Output files

- `report.json`
- `report.html`
- `extracted/`
- `jadx/` when enabled and available
- `apktool/` when enabled and available

## 5. Recommended ToolCase UI fields

- APK path picker
- Output folder picker
- Checkbox: Run JADX
- Checkbox: Run apktool
- Button: Analyze APK
- Button: Open HTML report
- Button: Open extracted folder

## 6. Security notes

Run unknown APKs in a sandboxed directory. Do not execute APK code. This module only extracts and scans static content.
