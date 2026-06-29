# ToolCase APK Reverse Engineering Suite

Standalone integration pack for ToolCase.

This module performs defensive APK analysis for APKs you own, are allowed to audit, or are testing in a lab environment.
It extracts APK metadata, manifest permissions, file inventory, DEX indicators, strings, URLs, suspicious secrets, native libraries, frameworks, and optional decompile output when external tools are installed.

## Features

- APK extraction to a controlled output folder
- AndroidManifest.xml detection
- Permission and component scan when decoded manifest text is available
- APK file inventory
- `classes.dex` detection
- URL, IP, email, package-name, endpoint and secret-pattern extraction
- Framework detection: Flutter, Unity, React Native, Cordova, Xamarin, Kotlin, native libraries
- Risk scoring with findings
- JSON report
- HTML report
- Optional JADX integration
- Optional apktool integration
- Optional MobSF handoff notes
- Version compare helper for two APK reports
- Safe extraction with path, symlink, entry-count, size and compression-ratio checks
- Repeatable output: directories created by an earlier run are cleaned before reuse

## Safe scope

This suite does not bypass licensing, DRM, authentication, anti-tamper, or encryption.
It is intended for app-security review, dependency review, own-app debugging, malware triage in a safe lab, and compliance checks.

Extraction defaults to at most 100,000 entries, 2 GiB total expanded data,
512 MiB per file and a 1000:1 compression ratio. Existing non-empty
`extracted/`, `jadx/` or `apktool/` folders are never overwritten unless the
output directory contains this suite's management marker.

## Quick start

```bash
python -m apk_reverse_suite.analyze --apk path/to/app.apk --out reports/app_audit
```

Optional external tools:

```bash
# JADX must be available on PATH as `jadx`
# apktool must be available on PATH as `apktool`
python -m apk_reverse_suite.analyze --apk app.apk --out reports/app_audit --jadx --apktool
```

## ToolCase integration

Copy `apk_reverse_suite/` into the ToolCase 5.2 source tree. The adjacent
`toolcase_registry_entry.json` contains the matching entries for
`manifest.json`, `tools_config.json`, and the `security-environment` category.
Merge those three entries, then run:

```bash
python improve.py --verify-install
```

For Python integrations that support callable entry points, use:

```json
{
  "id": "apk_reverse_suite",
  "name": "APK Reverse Engineering Suite",
  "category": "Android / Security",
  "entrypoint": "apk_reverse_suite.toolcase_integration:run_toolcase_apk_reverse",
  "description": "Analyze APK metadata, permissions, DEX indicators, URLs, secrets, libraries and optional decompiled output."
}
```
