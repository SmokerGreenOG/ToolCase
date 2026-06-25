#!/usr/bin/env python3
"""
apk_reverse.py — Android APK reverse engineering & decompilation tool.

Extracts and analyzes Android APK files:
  - Manifest parsing: package info, permissions (used+declared), activities,
    services, receivers, providers, intent filters, meta-data
  - APK structure: files, native libs, resources, signing META-INF
  - Signing verification: certificate info via apksigner
  - Resource decoding: ARSC binary parser, app strings, locale detection
  - Security scan: exported components audit, dangerous permissions
  - Size optimization: compression ratio, largest files, recommendations
  - URL & string scan: domains, API endpoints, deeplinks from DEX strings
  - Full decompilation: DEX → Java source via jadx
  - APK comparison: diff two APKs side-by-side

Dependencies (auto-detected):
  - aapt, apksigner (Android SDK build-tools)
  - jadx (standalone decompiler)

Gebruik:
    python apk_reverse.py <app.apk>
    python apk_reverse.py <app.apk> --output-dir ./decompiled/
    python apk_reverse.py <app.apk> --no-decompile --json
    python apk_reverse.py --compare <app1.apk> <app2.apk>
"""

__maker__ = "SmokerGreenOG"

import _protect
from safe_run import safe_run
import argparse
import json
import os
import re
import struct
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# ══════════════════════════════════════════════════════════════════════════════
# Tool Discovery
# ══════════════════════════════════════════════════════════════════════════════

JADX_PATHS = [
    Path("D:/Tools/jadx/bin/jadx.bat"),
    Path("D:/Tools/jadx/bin/jadx"),
]

ANDROID_SDK_PATHS = [
    Path("D:/Caches/Android-Sdk/Sdk"),
    Path(os.environ.get("ANDROID_SDK_ROOT", "")),
    Path(os.environ.get("ANDROID_HOME", "")),
]


def _find_sdk_tool(name: str) -> Path | None:
    for sdk in ANDROID_SDK_PATHS:
        bt_dir = sdk / "build-tools"
        if not bt_dir.is_dir():
            continue
        versions = sorted(
            [d for d in bt_dir.iterdir() if d.is_dir()],
            key=lambda x: [int(n) for n in x.name.split(".")],
            reverse=True,
        )
        for v in versions:
            for candidate in [name + ".exe", name + ".bat", name]:
                tool = v / candidate
                if tool.exists():
                    return tool
    return None


def find_aapt() -> Path | None:
    return _find_sdk_tool("aapt")


def find_apksigner() -> Path | None:
    return _find_sdk_tool("apksigner")


def find_jadx() -> Path | None:
    for p in JADX_PATHS:
        if p.exists():
            return p
    return None


def _run(cmd: list[str], timeout: int = 60) -> tuple[str, str, int]:
    try:
        r = safe_run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.stderr, r.returncode
    except FileNotFoundError:
        return "", f"Not found: {cmd[0]}", -1
    except TimeoutError:
        return "", "Timeout", -1


# ══════════════════════════════════════════════════════════════════════════════
# APK Structure Analysis
# ══════════════════════════════════════════════════════════════════════════════


def analyze_apk_structure(apk_path: Path) -> dict[str, Any]:
    """Analyze APK ZIP structure."""
    info: dict[str, Any] = {
        "file_size_mb": round(apk_path.stat().st_size / (1024 * 1024), 2),
        "files_total": 0,
        "dex_files": [],
        "native_libs": {},
        "resources": {"arsc": None, "manifest": None},
        "signing": [],
        "all_extensions": defaultdict(int),
    }
    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            for entry in zf.infolist():
                info["files_total"] += 1
                name = entry.filename
                ext = Path(name).suffix.lower()
                info["all_extensions"][ext] += 1
                if name.endswith(".dex"):
                    info["dex_files"].append(
                        {
                            "name": name,
                            "size_kb": round(entry.file_size / 1024, 1),
                        }
                    )
                elif name.startswith("lib/"):
                    arch = name.split("/")[1]
                    info["native_libs"].setdefault(arch, []).append(name)
                elif name == "resources.arsc":
                    info["resources"]["arsc"] = name
                elif name == "AndroidManifest.xml":
                    info["resources"]["manifest"] = name
                elif name.startswith("META-INF/") and any(
                    name.endswith(x) for x in [".RSA", ".DSA", ".EC", ".SF", ".MF"]
                ):
                    info["signing"].append(name)
    except zipfile.BadZipFile:
        info["error"] = "Not a valid ZIP/APK file"
    return info


# ══════════════════════════════════════════════════════════════════════════════
# Executable Analysis — SDK tools primary, binary parser fallback
# ══════════════════════════════════════════════════════════════════════════════


def find_dexdump() -> Path | None:
    return _find_sdk_tool("dexdump")


def find_apkanalyzer() -> Path | None:
    """Find apkanalyzer — Android Studio's APK inspection tool (inside SDK tools)."""
    # apkanalyzer is in <sdk>/tools/bin/ or <sdk>/cmdline-tools/latest/bin/
    for sdk in ANDROID_SDK_PATHS:
        for location in ["cmdline-tools/latest/bin", "tools/bin"]:
            bat = sdk / location / "apkanalyzer.bat"
            if bat.exists():
                return bat
            exe = sdk / location / "apkanalyzer"
            if exe.exists():
                return exe
    # Also try just 'apkanalyzer' on PATH
    try:
        r = safe_run(["where", "apkanalyzer"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip().splitlines()[0])
    except (OSError, OSError):
        pass
    return None


def analyze_executable(apk_path: Path) -> list[dict[str, Any]]:
    """Analyze DEX files — dexdump primary, binary parser fallback.

    Extracts: classes, methods, fields, strings, types, prototypes per DEX file.
    Uses Android SDK dexdump when available (official, reliable).
    Falls back to pure Python binary header parsing (portable, zero deps).
    """
    results: list[dict[str, Any]] = []
    structure = analyze_apk_structure(apk_path)
    dex_files = structure.get("dex_files", [])
    if not dex_files:
        return results

    dexdump = find_dexdump()

    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            for dex in dex_files:
                dex_name = dex["name"]
                dex_bytes = zf.read(dex_name)

                entry: dict[str, Any] = {"name": dex_name, "size_kb": dex["size_kb"]}

                if dexdump:
                    # Primary: use dexdump (official Android SDK tool)
                    import tempfile

                    with tempfile.NamedTemporaryFile(suffix=".dex", delete=False) as tmp:
                        tmp.write(dex_bytes)
                        tmp_path = tmp.name
                    stdout, _, _ = _run([str(dexdump), "-f", tmp_path], timeout=30)
                    os.unlink(tmp_path)

                    entry.update(
                        {
                            "classes": _parse_int(stdout, r"class_defs_size\s*:\s*(\d+)"),
                            "methods": _parse_int(stdout, r"method_ids_size\s*:\s*(\d+)"),
                            "fields": _parse_int(stdout, r"field_ids_size\s*:\s*(\d+)"),
                            "strings": _parse_int(stdout, r"string_ids_size\s*:\s*(\d+)"),
                            "types": _parse_int(stdout, r"type_ids_size\s*:\s*(\d+)"),
                            "prototypes": _parse_int(stdout, r"proto_ids_size\s*:\s*(\d+)"),
                            "data_size_kb": round(
                                _parse_int(stdout, r"data_size\\s*:\\s*(\\d+)") / 1024, 1
                            ),
                            "dex_version": _parse_str(stdout, r"DEX version '(\d+)'") or "?",
                            "method": "dexdump",
                        }
                    )
                else:
                    # Fallback: pure Python binary header parser
                    if len(dex_bytes) >= 112:
                        entry.update(
                            {
                                "classes": struct.unpack_from("<I", dex_bytes, 96)[0],
                                "methods": struct.unpack_from("<I", dex_bytes, 88)[0],
                                "fields": struct.unpack_from("<I", dex_bytes, 80)[0],
                                "strings": struct.unpack_from("<I", dex_bytes, 56)[0],
                                "types": struct.unpack_from("<I", dex_bytes, 64)[0],
                                "prototypes": struct.unpack_from("<I", dex_bytes, 72)[0],
                                "data_size_kb": round(
                                    struct.unpack_from("<I", dex_bytes, 104)[0] / 1024, 1
                                ),
                                "dex_version": dex_bytes[4:7].decode("ascii", errors="replace"),
                                "method": "binary",
                            }
                        )

                results.append(entry)
    except Exception:
        pass

    return results


def _parse_int(text: str, pattern: str) -> int:
    m = re.search(pattern, text)
    return int(m.group(1)) if m else 0


def _parse_str(text: str, pattern: str) -> str:
    m = re.search(pattern, text)
    return m.group(1) if m else ""


# ══════════════════════════════════════════════════════════════════════════════
# DEX String Extraction (lightweight, no dexdump)
# ══════════════════════════════════════════════════════════════════════════════


def _extract_dex_strings(apk_path: Path) -> list[str]:
    """Extract readable strings from DEX files inside the APK.

    Parses the DEX string_id table directly (binary format) — no dexdump needed.
    """
    all_strings: list[str] = []
    structure = analyze_apk_structure(apk_path)
    dex_files = structure.get("dex_files", [])

    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            for dex in dex_files:
                dex_bytes = zf.read(dex["name"])
                if len(dex_bytes) < 112:
                    continue
                string_ids_size = struct.unpack_from("<I", dex_bytes, 56)[0]
                string_ids_off = struct.unpack_from("<I", dex_bytes, 60)[0]
                if string_ids_size == 0 or string_ids_off == 0:
                    continue

                for i in range(min(string_ids_size, 10000)):
                    offset_addr = string_ids_off + i * 4
                    if offset_addr + 4 > len(dex_bytes):
                        break
                    str_offset = struct.unpack_from("<I", dex_bytes, offset_addr)[0]
                    if str_offset >= len(dex_bytes):
                        continue

                    pos = str_offset
                    length = 0
                    shift = 0
                    while pos < len(dex_bytes) and shift < 35:
                        byte = dex_bytes[pos]
                        pos += 1
                        length |= (byte & 0x7F) << shift
                        shift += 7
                        if byte & 0x80 == 0:
                            break
                    if length == 0 or pos + length > len(dex_bytes):
                        continue

                    try:
                        raw = dex_bytes[pos : pos + length]
                        raw = raw.replace(b"\xc0\x80", b"\x00")
                        s = raw.decode("utf-8", errors="replace")
                        if s.strip():
                            all_strings.append(s)
                    except (UnicodeDecodeError, IndexError):
                        pass
    except Exception:
        pass

    return all_strings


# ══════════════════════════════════════════════════════════════════════════════
# URL & String Scanning
# ══════════════════════════════════════════════════════════════════════════════


def scan_urls(strings: list[str], manifest_xml: str = "") -> dict[str, Any]:
    """Scan collected strings for URLs, domains, API endpoints, deeplinks."""
    urls: dict[str, Any] = {
        "http_urls": [],
        "https_urls": [],
        "domains": set(),
        "api_endpoints": [],
        "deep_links": [],
        "ip_addresses": [],
        "strings_count": len(strings),
    }

    url_pattern = re.compile(
        r"(https?://(?:[-\w.]|%[\da-fA-F]{2})+(?::\d+)?(?:/[-\w$.+!*'(),;:@&=?/~#%]*)*)",
        re.IGNORECASE,
    )
    ip_pattern = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")

    for s in strings:
        for url in url_pattern.findall(s):
            url = url.rstrip(".,;:!?)")
            if len(url) < 10:
                continue
            if url.startswith("https://"):
                if url not in urls["https_urls"]:
                    urls["https_urls"].append(url)
            elif url.startswith("http://"):
                if url not in urls["http_urls"]:
                    urls["http_urls"].append(url)
            try:
                domain = url.split("/")[2].lower()
                if not any(domain.startswith(p) for p in ("localhost", "10.", "192.168", "127.")):
                    urls["domains"].add(domain)
            except (IndexError, ValueError):
                pass
            if any(x in url.lower() for x in ("/api/", "/v1/", "/v2/", "/rest/", "/graphql")):
                if url not in urls["api_endpoints"]:
                    urls["api_endpoints"].append(url)

        for ip in ip_pattern.findall(s):
            parts = ip.split(".")
            if all(0 <= int(p) <= 255 for p in parts):
                if ip not in urls["ip_addresses"]:
                    urls["ip_addresses"].append(ip)

    if manifest_xml:
        schemes = re.findall(
            r"""android:scheme\s*=\s*['"]([^'"]+)['"]""", manifest_xml, re.IGNORECASE
        )
        hosts = re.findall(r"""android:host\s*=\s*['"]([^'"]+)['"]""", manifest_xml, re.IGNORECASE)
        for i, host in enumerate(hosts):
            scheme = schemes[i] if i < len(schemes) else "https"
            dl = f"{scheme}://{host}"
            if dl not in urls["deep_links"]:
                urls["deep_links"].append(dl)

    urls["domains"] = sorted(urls["domains"])
    return urls


# ══════════════════════════════════════════════════════════════════════════════
# Signing Verification
# ══════════════════════════════════════════════════════════════════════════════


def verify_signing(apk_path: Path, apksigner: Path) -> dict[str, Any]:
    """Verify APK signing via apksigner, extract certificate info."""
    result: dict[str, Any] = {"verified": False, "scheme": None, "certificates": []}
    stdout, stderr, rc = _run(
        [str(apksigner), "verify", "--verbose", "--print-certs", str(apk_path)], timeout=30
    )
    if rc == 0 or "Verifies" in stdout:
        result["verified"] = True

    m_dn = re.search(r"certificate DN:\s*(.+)", stdout)
    m_sha = re.search(r"certificate SHA-256 digest:\s*(\S+)", stdout)
    if m_dn:
        result["certificates"].append(
            {"dn": m_dn.group(1).strip(), "sha256": m_sha.group(1) if m_sha else None}
        )
    for block in re.split(r"Signer #\d+", stdout)[1:]:
        m_dn = re.search(r"certificate DN:\s*(.+)", block)
        m_sha = re.search(r"certificate SHA-256 digest:\s*(\S+)", block)
        if m_dn and not any(c.get("dn") == m_dn.group(1).strip() for c in result["certificates"]):
            result["certificates"].append(
                {"dn": m_dn.group(1).strip(), "sha256": m_sha.group(1) if m_sha else None}
            )

    if re.search(r"v3(?:\.\d)? scheme[^:]*:\s*true", stdout):
        result["scheme"] = "v3"
    elif re.search(r"v2 scheme[^:]*:\s*true", stdout):
        result["scheme"] = "v2"
    elif re.search(r"(?:v1|JAR) signing[^:]*:\s*true", stdout):
        result["scheme"] = "v1 (JAR)"
    if stderr and not result["verified"]:
        result["error"] = stderr.strip()[:300]
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Manifest Parsing
# ══════════════════════════════════════════════════════════════════════════════


def parse_aapt_badging(output: str) -> dict[str, Any]:
    """Parse aapt dump badging output."""
    data: dict[str, Any] = {
        "package": None,
        "version_code": None,
        "version_name": None,
        "sdk_version": None,
        "target_sdk": None,
        "compile_sdk": None,
        "label": None,
        "permissions_used": [],
        "permissions_declared": [],
        "features": [],
        "densities": [],
        "locales": [],
        "native_code": [],
        "supports_screens": [],
    }
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("package:"):
            for key, pattern in [
                ("package", r"name='([^']+)'"),
                ("version_code", r"versionCode='([^']+)'"),
                ("version_name", r"versionName='([^']+)'"),
                ("compile_sdk", r"compileSdkVersion='([^']+)'"),
            ]:
                m = re.search(pattern, line)
                if m:
                    data[key] = m.group(1)
        elif line.startswith("sdkVersion:"):
            data["sdk_version"] = line.split("'")[1] if "'" in line else line.split(":")[1].strip()
        elif line.startswith("targetSdkVersion:"):
            data["target_sdk"] = line.split("'")[1] if "'" in line else line.split(":")[1].strip()
        elif line.startswith("uses-permission:"):
            m = re.search(r"name='([^']+)'", line)
            if m:
                data["permissions_used"].append(m.group(1))
        elif line.startswith("permission:"):
            m = re.search(r"name='([^']+)'", line)
            if m:
                data["permissions_declared"].append(m.group(1))
        elif line.startswith("uses-feature"):
            feat = {}
            m = re.search(r"name='([^']+)'", line)
            if m:
                feat["name"] = m.group(1)
            m = re.search(r"required='([^']+)'", line)
            if m:
                feat["required"] = m.group(1) == "true"
            data["features"].append(feat)
        elif line.startswith("application-label:"):
            if data["label"] is None:
                data["label"] = line.split("'")[1] if "'" in line else line.split(":")[1].strip()
        elif line.startswith("application:"):
            m = re.search(r"label='([^']+)'", line)
            if m:
                data["label"] = m.group(1)
        elif line.startswith("densities:"):
            data["densities"] = [d.strip() for d in line.split(":")[1].strip().split(",")]
        elif line.startswith("locales:"):
            data["locales"] = [l.strip() for l in line.split(":")[1].strip().split(",")]
        elif line.startswith("native-code:"):
            data["native_code"] = [
                a.strip() for a in line.split(":")[1].strip().split(",") if a.strip()
            ]
        elif line.startswith("supports-screens:"):
            data["supports_screens"] = line.split(":")[1].strip()
    return data


def parse_aapt_xmltree(output: str) -> dict[str, Any]:
    """Parse aapt dump xmltree for components."""
    data: dict[str, Any] = {
        "activities": [],
        "services": [],
        "receivers": [],
        "providers": [],
        "meta_data": [],
        "intent_filters": defaultdict(list),
    }
    COMPONENT_TAGS = {"activity", "activity-alias", "service", "receiver", "provider"}
    TYPE_MAP = {
        "activity": "activities",
        "activity-alias": "activities",
        "service": "services",
        "receiver": "receivers",
        "provider": "providers",
    }
    current: dict[str, Any] | None = None
    current_type: str | None = None
    current_depth: int = 99
    in_filter: bool = False
    pending_filter_actions: list[str] | None = None

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(" "))
        m_tag = re.match(r"E: (\S+)", stripped)
        if m_tag:
            tag = m_tag.group(1)
            if tag == "intent-filter":
                in_filter = True
                pending_filter_actions = []
            elif tag in ("action", "category") and in_filter and pending_filter_actions is not None:
                m_name = re.search(r'android:name(?:\([^)]+\))?="([^"]+)"', stripped)
                if m_name:
                    pending_filter_actions.append(m_name.group(1))
            if current and indent <= current_depth and tag in COMPONENT_TAGS:
                if in_filter and pending_filter_actions and current.get("name"):
                    data["intent_filters"][current["name"]].extend(
                        {"action": a} for a in pending_filter_actions
                    )
                in_filter = False
                pending_filter_actions = None
                if current.get("name"):
                    data[TYPE_MAP.get(current_type, "activities")].append(current)
                current = None
                current_type = None
            if tag in COMPONENT_TAGS:
                current_type = tag.removesuffix("-alias")
                current = {"name": None, "exported": None, "permission": None}
                current_depth = indent
                m_name = re.search(r'android:name(?:\([^)]+\))?="([^"]+)"', stripped)
                if m_name:
                    current["name"] = m_name.group(1)
            continue
        if current:
            if "android:name" in stripped and '="' in stripped and not current.get("name"):
                m = re.search(r'="([^"]*)"', stripped)
                if m:
                    current["name"] = m.group(1)
            if "android:exported" in stripped:
                m = re.search(r'="([^"]*)"', stripped)
                if m:
                    current["exported"] = m.group(1)
                elif "0xffffffff" in stripped:
                    current["exported"] = "true"
                elif "0x0" in stripped and "(type 0x12)" in stripped:
                    current["exported"] = "false"
            elif "android:permission" in stripped and '="' in stripped:
                m = re.search(r'="([^"]*)"', stripped)
                current["permission"] = m.group(1) if m else None
            elif current_type == "provider" and "android:authorities" in stripped:
                m = re.search(r'="([^"]*)"', stripped)
                if m:
                    current["authority"] = m.group(1)
        if "E: meta-data" in stripped and current:
            m_name = re.search(r'android:name(?:\([^)]+\))?="([^"]+)"', stripped)
            m_value = re.search(r'android:value(?:\([^)]+\))?="([^"]+)"', stripped)
            if m_name:
                data["meta_data"].append(
                    {
                        "name": m_name.group(1),
                        "value": m_value.group(1) if m_value else None,
                        "component": current.get("name"),
                        "type": current_type,
                    }
                )
    if in_filter and pending_filter_actions and current and current.get("name"):
        data["intent_filters"][current["name"]].extend(
            {"action": a} for a in pending_filter_actions
        )
    if current and current.get("name"):
        data[TYPE_MAP.get(current_type, "activities")].append(current)
    return data


# ══════════════════════════════════════════════════════════════════════════════
# Decompilation (jadx)
# ══════════════════════════════════════════════════════════════════════════════


def run_jadx(apk_path: Path, output_dir: Path, threads: int = 4) -> dict[str, Any]:
    """Run jadx decompilation."""
    jadx = find_jadx()
    if not jadx:
        return {"error": "jadx not found. Install from https://github.com/skylot/jadx"}
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(jadx), "-d", str(output_dir), "-j", str(threads), "--show-bad-code", str(apk_path)]
    stdout, stderr, rc = _run(cmd, timeout=600)
    java_files = list(output_dir.rglob("*.java"))
    return {
        "success": len(java_files) > 0,
        "exit_code": rc,
        "output_dir": str(output_dir),
        "java_files_count": len(java_files),
        "total_files_count": len(list(output_dir.rglob("*"))),
        "errors": [l for l in stderr.splitlines() if "ERROR" in l][:10] if stderr else [],
    }


# ══════════════════════════════════════════════════════════════════════════════
# APK Comparison
# ══════════════════════════════════════════════════════════════════════════════


def compare_apks(path1: Path, path2: Path) -> dict[str, Any]:
    """Compare two APKs."""
    s1 = analyze_apk_structure(path1)
    s2 = analyze_apk_structure(path2)
    size1, size2 = path1.stat().st_size, path2.stat().st_size
    aapt = find_aapt()
    m1, m2 = {}, {}
    if aapt:
        b1, _, _ = _run([str(aapt), "dump", "badging", str(path1)], timeout=30)
        b2, _, _ = _run([str(aapt), "dump", "badging", str(path2)], timeout=30)
        m1 = parse_aapt_badging(b1) if b1 else {}
        m2 = parse_aapt_badging(b2) if b2 else {}
    return {
        "apk1": {
            "path": str(path1),
            "size_mb": round(size1 / (1024 * 1024), 2),
            "files": s1["files_total"],
            "dex_count": len(s1["dex_files"]),
        },
        "apk2": {
            "path": str(path2),
            "size_mb": round(size2 / (1024 * 1024), 2),
            "files": s2["files_total"],
            "dex_count": len(s2["dex_files"]),
        },
        "size_diff_mb": round((size2 - size1) / (1024 * 1024), 2),
        "size_diff_pct": round((size2 - size1) / size1 * 100, 1) if size1 > 0 else 0,
        "package_match": m1.get("package") == m2.get("package"),
        "version_change": f"{m1.get('version_name')} → {m2.get('version_name')}",
        "perms_added": [
            p for p in m2.get("permissions_used", []) if p not in m1.get("permissions_used", [])
        ],
        "perms_removed": [
            p for p in m1.get("permissions_used", []) if p not in m2.get("permissions_used", [])
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# Security Vulnerability Scan
# ══════════════════════════════════════════════════════════════════════════════


def analyze_security(manifest: dict[str, Any], structure: dict[str, Any]) -> list[dict[str, Any]]:
    """Scan for common Android security misconfigurations."""
    findings: list[dict[str, Any]] = []
    for a in [
        c for c in manifest.get("activities", []) if c.get("exported") in ("true", "0xffffffff")
    ]:
        if not a.get("permission"):
            findings.append(
                {
                    "severity": "medium",
                    "title": "Exported activity without permission protection",
                    "detail": f"Activity '{a.get('name', '?')}' is exported without android:permission.",
                    "component": a.get("name"),
                }
            )
    for s in [
        c for c in manifest.get("services", []) if c.get("exported") in ("true", "0xffffffff")
    ]:
        if not s.get("permission"):
            findings.append(
                {
                    "severity": "high",
                    "title": "Exported service without permission protection",
                    "detail": f"Service '{s.get('name', '?')}' is exported without android:permission.",
                    "component": s.get("name"),
                }
            )
    for r in [
        c for c in manifest.get("receivers", []) if c.get("exported") in ("true", "0xffffffff")
    ]:
        if not r.get("permission"):
            findings.append(
                {
                    "severity": "medium",
                    "title": "Exported receiver without permission protection",
                    "detail": f"Receiver '{r.get('name', '?')}' is exported without android:permission.",
                    "component": r.get("name"),
                }
            )
    for p in [
        c for c in manifest.get("providers", []) if c.get("exported") in ("true", "0xffffffff")
    ]:
        if not p.get("authority"):
            findings.append(
                {
                    "severity": "high",
                    "title": "Exported content provider without permission",
                    "detail": f"Provider '{p.get('name', '?')}' is exported without permission.",
                    "component": p.get("name"),
                }
            )
    dangerous = [
        p
        for p in manifest.get("permissions_used", [])
        if any(
            d in p
            for d in [
                "CAMERA",
                "RECORD_AUDIO",
                "LOCATION",
                "CONTACTS",
                "SMS",
                "CALL_LOG",
                "BODY_SENSORS",
                "READ_EXTERNAL_STORAGE",
                "ACCESS_FINE_LOCATION",
                "ACCESS_BACKGROUND_LOCATION",
                "READ_CONTACTS",
                "READ_PHONE_STATE",
            ]
        )
    ]
    if dangerous:
        findings.append(
            {
                "severity": "info",
                "title": f"Dangerous permissions: {len(dangerous)}",
                "detail": ", ".join(p.split(".")[-1] for p in dangerous[:10]),
            }
        )
    if manifest.get("permissions_declared"):
        findings.append(
            {
                "severity": "info",
                "title": f"Custom permissions declared: {len(manifest['permissions_declared'])}",
                "detail": "Verify protectionLevel is set correctly.",
            }
        )
    return findings


# ══════════════════════════════════════════════════════════════════════════════
# Resource Decoding
# ══════════════════════════════════════════════════════════════════════════════


def decode_resources(apk_path: Path) -> dict[str, Any]:
    """Decode resources.arsc — extract app strings and locale info."""
    result: dict[str, Any] = {
        "total_resources": 0,
        "string_count": 0,
        "locales": [],
        "top_strings": [],
    }
    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            if "resources.arsc" not in zf.namelist():
                result["note"] = "No resources.arsc found"
                return result
            arsc_data = zf.read("resources.arsc")
            if len(arsc_data) < 16:
                return result
            strings: list[dict[str, str]] = []
            locales_seen: set[str] = set()
            pos = 16
            while pos < len(arsc_data) - 4 and len(strings) < 500:
                byte1, byte2 = arsc_data[pos], arsc_data[pos + 1] if pos + 1 < len(arsc_data) else 0
                if 4 <= byte1 <= 120 and byte2 >= 0x20:
                    try:
                        candidate = arsc_data[pos + 1 : pos + 1 + byte1].decode(
                            "utf-8", errors="ignore"
                        )
                        if candidate.isprintable() and len(candidate) >= 2:
                            if candidate not in {s["value"] for s in strings}:
                                strings.append({"value": candidate, "locale": "default"})
                    except (UnicodeDecodeError, IndexError):
                        pass
                if byte1 >= 2 and byte2 == 0:
                    try:
                        raw16 = arsc_data[pos + 2 : pos + 2 + byte1 * 2]
                        candidate = raw16.decode("utf-16-le", errors="ignore")
                        if candidate.isprintable() and len(candidate) >= 2:
                            if candidate not in {s["value"] for s in strings}:
                                strings.append({"value": candidate, "locale": "default"})
                    except (UnicodeDecodeError, IndexError):
                        pass
                pos += 1
            seen = set()
            unique = []
            for s in strings:
                if s["value"] not in seen:
                    seen.add(s["value"])
                    unique.append(s)
            result["total_resources"] = len(unique)
            result["string_count"] = len(unique)
            result["top_strings"] = unique[:30]
            for name in zf.namelist():
                if name.startswith("res/values-") and name.endswith("/"):
                    loc = name.replace("res/values-", "").rstrip("/")
                    if loc and loc not in locales_seen:
                        locales_seen.add(loc)
            result["locales"] = sorted(locales_seen)
    except Exception as e:
        result["error"] = str(e)[:200]
    return result


# ══════════════════════════════════════════════════════════════════════════════
# APK Size Optimization
# ══════════════════════════════════════════════════════════════════════════════


def sizeof_fmt(num: float, suffix: str = "B") -> str:
    for unit in ("", "K", "M", "G"):
        if abs(num) < 1024:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024
    return f"{num:.1f} T{suffix}"


def analyze_size(apk_path: Path, structure: dict[str, Any]) -> dict[str, Any]:
    """Analyze APK size — compression, largest files, recommendations."""
    info: dict[str, Any] = {
        "total_size_mb": structure.get("file_size_mb", 0),
        "largest_files": [],
        "compression_ratio": 0,
        "recommendations": [],
    }
    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            entries = []
            total_c, total_u = 0, 0
            for entry in zf.infolist():
                c, u = entry.compress_size, entry.file_size
                total_c += c
                total_u += u
                ratio = round((1 - c / u) * 100, 1) if u > 0 else 0
                entries.append(
                    {
                        "name": entry.filename,
                        "size_kb": round(u / 1024, 1),
                        "compressed_kb": round(c / 1024, 1),
                        "ratio": ratio,
                    }
                )
            entries.sort(key=lambda x: -x["size_kb"])
            info["largest_files"] = entries[:15]
            if total_u > 0:
                info["compression_ratio"] = round((1 - total_c / total_u) * 100, 1)
            recs = info["recommendations"]
            large = [e for e in entries if e["size_kb"] > 500 and e["ratio"] < 5]
            if large:
                recs.append(
                    f"Large uncompressed assets: {len(large)} files ({sizeof_fmt(sum(e['size_kb'] for e in large) * 1024)}). Consider WebP/AVIF."
                )
            ext_counts: dict[str, int] = defaultdict(int)
            for e in entries:
                ext_counts[Path(e["name"]).suffix.lower()] += 1
            for ext, count in ext_counts.items():
                if count > 50:
                    recs.append(
                        f"{count} files with extension '{ext}' — check for duplicates/unused resources"
                    )
            native = structure.get("native_libs", {})
            if len(native) > 2:
                recs.append(
                    f"Native libs for {len(native)} ABIs ({', '.join(sorted(native.keys()))}). Consider AAB to split per device."
                )
            dex_kb = sum(e["size_kb"] for e in entries if e["name"].endswith(".dex"))
            if info["total_size_mb"] > 0 and dex_kb / (info["total_size_mb"] * 1024) * 100 < 30:
                recs.append(
                    f"DEX is only {dex_kb / (info['total_size_mb'] * 1024) * 100:.0f}% of APK — review asset sizes."
                )
    except Exception as e:
        info["error"] = str(e)[:200]
    return info


# ══════════════════════════════════════════════════════════════════════════════
# Report Generation
# ══════════════════════════════════════════════════════════════════════════════


def generate_report(
    apk_path: Path,
    aapt_path: Path,
    output_dir: Path | None = None,
    no_decompile: bool = False,
    threads: int = 4,
) -> dict[str, Any]:
    """Generate full reverse engineering report."""
    report: dict[str, Any] = {
        "file": str(apk_path),
        "analyzed_at": datetime.now().isoformat(),
        "structure": analyze_apk_structure(apk_path),
        "manifest": {},
        "executable": [],
        "strings": [],
        "urls": {},
        "signing": {},
        "security": [],
        "resources": {},
        "size_optimization": {},
        "decompilation": None,
    }
    if "error" in report["structure"]:
        return report

    badging_stdout, _, _ = _run([str(aapt_path), "dump", "badging", str(apk_path)], timeout=30)
    if badging_stdout:
        report["manifest"] = parse_aapt_badging(badging_stdout)

    xmltree_stdout, _, _ = _run(
        [str(aapt_path), "dump", "xmltree", str(apk_path), "AndroidManifest.xml"], timeout=30
    )
    if xmltree_stdout:
        report["manifest"].update(parse_aapt_xmltree(xmltree_stdout))

    # Extract DEX strings (lightweight, no dexdump)
    report["executable"] = analyze_executable(apk_path)
    report["strings"] = _extract_dex_strings(apk_path)
    report["urls"] = scan_urls(report["strings"], xmltree_stdout)

    apksigner = find_apksigner()
    if apksigner:
        report["signing"] = verify_signing(apk_path, apksigner)

    report["security"] = analyze_security(report["manifest"], report["structure"])
    report["resources"] = decode_resources(apk_path)
    report["size_optimization"] = analyze_size(apk_path, report["structure"])

    if not no_decompile:
        out = output_dir or Path(str(apk_path) + "_decompiled")
        report["decompilation"] = run_jadx(apk_path, out, threads)

    return report


def print_report(report: dict[str, Any], json_mode: bool = False) -> None:
    """Print human-readable report."""
    if json_mode:
        report_copy = json.loads(json.dumps(report, default=list, ensure_ascii=False))
        print(json.dumps(report_copy, indent=2, ensure_ascii=False))
        return

    s = report.get("structure", {})
    m = report.get("manifest", {})
    urls = report.get("urls", {})
    sig = report.get("signing", {})
    d = report.get("decompilation")

    def _exp(c):
        return " [EXPORTED]" if c.get("exported") in ("true", "0xffffffff") else ""

    print(f"\n{'=' * 70}\n  🔍 APK REVERSE ENGINEERING REPORT\n{'=' * 70}")
    print(f"  File        : {report.get('file')}")
    print(f"  Analyzed    : {report.get('analyzed_at', 'N/A')}")
    if s.get("error"):
        print(f"\n  ❌ ERROR: {s['error']}")
        return

    # Structure
    print(f"\n{'─' * 70}\n  📦 APK STRUCTURE\n{'─' * 70}")
    print(f"  Size        : {s['file_size_mb']} MB\n  Total files : {s['files_total']}")
    for dex in s.get("dex_files", []):
        print(f"    • {dex['name']} ({dex['size_kb']} KB)")
    native = s.get("native_libs", {})
    if native:
        print(
            f"  Native libs : {sum(len(v) for v in native.values())} across {len(native)} architectures"
        )
        for arch, libs in sorted(native.items()):
            print(f"    • {arch}: {len(libs)} .so files")

    # Executable Analysis (SDK dexdump primary, binary fallback)
    dx = report.get("executable", [])
    if dx:
        print(f"\n{'─' * 70}\n  📊 EXECUTABLE ANALYSIS\n{'─' * 70}")
        for d in dx:
            print(f"  Method        : {d.get('method', '?')}")
            print(f"  DEX version   : {d.get('dex_version', '?')}")
            print(f"  Classes       : {d['classes']:,}")
            print(f"  Methods       : {d['methods']:,}")
            print(f"  Fields        : {d['fields']:,}")
            print(f"  Types         : {d['types']:,}")
            print(f"  Prototypes    : {d['prototypes']:,}")
            print(f"  Strings       : {d['strings']:,}")
            print(f"  Data size     : {d['data_size_kb']} KB")

    # URL Scan
    if urls:
        print(f"\n{'─' * 70}\n  🌐 URL & STRING SCAN\n{'─' * 70}")
        print(f"  Strings extracted: {urls.get('strings_count', 0)}")
        print(
            f"  HTTP URLs : {len(urls.get('http_urls', []))}  HTTPS: {len(urls.get('https_urls', []))}"
        )
        print(
            f"  API endpoints: {len(urls.get('api_endpoints', []))}  Domains: {len(urls.get('domains', []))}"
        )
        if urls.get("domains"):
            print(f"  🌍 Domains:")
            [print(f"    • {d}") for d in urls["domains"][:10]]
        if urls.get("api_endpoints"):
            print(f"  ⚡ API Endpoints:")
            [print(f"    • {ep}") for ep in urls["api_endpoints"][:5]]

    # Signing
    if sig:
        print(f"\n{'─' * 70}\n  🔏 SIGNING VERIFICATION\n{'─' * 70}")
        print(
            f"  Verified : {'✅ Yes' if sig.get('verified') else '❌ No'}  Scheme: {sig.get('scheme', '?')}"
        )
        for i, cert in enumerate(sig.get("certificates", [])):
            print(f"\n  Certificate #{i + 1}:")
            if cert.get("dn"):
                for part in cert["dn"].split(", "):
                    print(f"    {part}")
            if cert.get("sha256"):
                print(f"    SHA-256: {cert['sha256']}")

    # Manifest
    print(f"\n{'─' * 70}\n  📋 MANIFEST\n{'─' * 70}")
    for k in ["package", "label", "sdk_version", "target_sdk", "compile_sdk"]:
        if m.get(k):
            print(f"  {k.replace('_', ' ').title():12}: {m[k]}")
    if m.get("version_name"):
        print(f"  Version     : {m['version_name']} (code {m.get('version_code', '?')})")
    for label, key in [
        ("Used Permissions", "permissions_used"),
        ("Declared Permissions", "permissions_declared"),
    ]:
        items = m.get(key, [])
        if items:
            print(f"\n  🔐 {label} ({len(items)}):")
            for p in items:
                print(f"    • {p.split('.')[-1]}  ({p})")
    for label, key in [
        ("Activities", "activities"),
        ("Services", "services"),
        ("Receivers", "receivers"),
    ]:
        items = m.get(key, [])
        if items:
            print(
                f"\n  {'🖥' if 'Act' in label else '⚙' if 'Serv' in label else '📡'} {label} ({len(items)}):"
            )
            for c in items:
                print(f"    • {(c.get('name') or '?').split('.')[-1]}{_exp(c)}")
    provs = m.get("providers", [])
    if provs:
        print(f"\n  🗄  Providers ({len(provs)}):")
        for p in provs:
            print(f"    • {(p.get('name') or '?').split('.')[-1]}{_exp(p)}")
            if p.get("authority"):
                print(f"      authority: {p['authority']}")
    if m.get("features"):
        print(f"\n  🔧 Features ({len(m['features'])}):")
    if m.get("native_code"):
        print(f"\n  🏗 Native arches: {', '.join(m['native_code'])}")

    # Security
    sec = report.get("security", [])
    if sec:
        print(f"\n{'─' * 70}\n  🔒 SECURITY SCAN\n{'─' * 70}")
        counts = {"high": 0, "medium": 0, "low": 0, "info": 0}
        for f in sec:
            counts[f.get("severity", "low")] = counts.get(f.get("severity", "low"), 0) + 1
        if sum(counts.values()) == 0:
            print("  ✅ No issues")
        else:
            print(f"  Findings: {' | '.join(f'{k.upper()}={v}' for k, v in counts.items() if v)}")
            for f in sec:
                icon = {"high": "🟠", "medium": "🟡", "low": "🟢", "info": "💡"}.get(
                    f["severity"], "⚪"
                )
                print(f"\n  {icon} [{f['severity'].upper()}] {f['title']}")
                if f.get("component"):
                    print(f"      {f['component'].split('.')[-1]}")
                if f.get("detail"):
                    print(f"      {f['detail']}")

    # Resources
    res = report.get("resources", {})
    if res and not res.get("note"):
        print(f"\n{'─' * 70}\n  📱 RESOURCE DECODING\n{'─' * 70}")
        if res.get("error"):
            print(f"  ❌ {res['error']}")
        else:
            print(
                f"  Strings found: {res.get('string_count', 0)}  Locales: {', '.join(res.get('locales', [])[:10])}"
            )
            top = [
                s
                for s in res.get("top_strings", [])
                if s["value"].isascii() and len(s["value"]) >= 3
            ][:8]
            if top:
                print(f"\n  📝 App Strings:")
                for s in top:
                    print(f'    • "{s["value"][:70]}"')

    # Size
    sz = report.get("size_optimization", {})
    if sz and not sz.get("error"):
        print(f"\n{'─' * 70}\n  🧹 SIZE OPTIMIZATION\n{'─' * 70}")
        print(
            f"  Size: {sz.get('total_size_mb', 0)} MB  Compression: {sz.get('compression_ratio', 0)}%"
        )
        recs = sz.get("recommendations", [])
        if recs:
            print(f"\n  💡 Recommendations:")
            for r in recs:
                print(f"    • {r}")
        largest = sz.get("largest_files", [])[:5]
        if largest:
            print(f"\n  📦 Largest Files:")
            for f in largest:
                print(f"    • {f['size_kb']:>8.0f} KB  ({f['ratio']}%)  {f['name'][:55]}")

    # Decompilation
    if d:
        print(f"\n{'─' * 70}\n  ☕ DECOMPILATION (jadx)\n{'─' * 70}")
        if d.get("error"):
            print(f"  ❌ {d['error']}")
        elif d.get("success"):
            print(
                f"  Status: ✅ Success  Java: {d['java_files_count']}  Files: {d['total_files_count']}"
            )
            if d.get("errors"):
                print(f"  ⚠ Non-fatal errors: {len(d['errors'])}")
        else:
            print(f"  ❌ Failed (no Java, exit {d['exit_code']})")

    print(f"\n{'=' * 70}\n")


def print_comparison(comp: dict[str, Any], json_mode: bool = False) -> None:
    """Print APK comparison report."""
    if json_mode:
        print(json.dumps(comp, indent=2, ensure_ascii=False))
        return
    a1, a2 = comp["apk1"], comp["apk2"]
    print(f"\n{'=' * 70}\n  🔄 APK COMPARISON\n{'=' * 70}")
    print(
        f"  APK 1: {a1['path']}\n         {a1['size_mb']} MB | {a1['files']} files | {a1['dex_count']} DEX"
    )
    print(
        f"  APK 2: {a2['path']}\n         {a2['size_mb']} MB | {a2['files']} files | {a2['dex_count']} DEX"
    )
    print(f"\n  Size diff : {comp['size_diff_mb']:+.2f} MB ({comp['size_diff_pct']:+.1f}%)")
    print(f"  Package   : {'✅ Same' if comp.get('package_match') else '❌ Different'}")
    if comp.get("version_change"):
        print(f"  Version   : {comp['version_change']}")
    for label, key in [("added", "perms_added"), ("removed", "perms_removed")]:
        items = comp.get(key, [])
        if items:
            print(f"\n  🔐 Permissions {label} ({len(items)}):")
            for p in items:
                print(f"    {'+' if 'add' in label else '-'} {p}")
    print(f"\n{'=' * 70}\n")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        description="🔍 APK Reverse Engineering — decompile & analyze Android APKs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  python apk_reverse.py app.apk\n  python apk_reverse.py app.apk -o ./out/ --json\n  python apk_reverse.py --compare v1.apk v2.apk",
    )
    parser.add_argument("apk", nargs="?", help="Path to APK file")
    parser.add_argument("--output-dir", "-o", help="Output directory for decompiled source")
    parser.add_argument("--no-decompile", action="store_true", help="Skip jadx decompilation")
    parser.add_argument("--threads", "-j", type=int, default=4, help="jadx thread count")
    parser.add_argument("--json", "-J", action="store_true", help="Output as JSON")
    parser.add_argument("--compare", nargs=2, metavar=("APK1", "APK2"), help="Compare two APKs")
    parser.add_argument("--version", action="version", version="apk_reverse v2.1.0")
    args = parser.parse_args()

    if args.compare:
        p1, p2 = Path(args.compare[0]), Path(args.compare[1])
        if not p1.exists() or not p2.exists():
            print("Error: APK not found", file=sys.stderr)
            sys.exit(1)
        print_comparison(compare_apks(p1, p2), args.json)
        return
    if not args.apk:
        parser.print_help()
        sys.exit(1)
    apk_path = Path(args.apk)
    if not apk_path.exists():
        print(f"Error: APK not found: {args.apk}", file=sys.stderr)
        sys.exit(1)
    aapt = find_aapt()
    if not aapt:
        print("Error: aapt not found. Install Android SDK build-tools.", file=sys.stderr)
        sys.exit(1)
    if not args.json:
        print(f"🔍 Analyzing {apk_path.name}...")
    output_dir = Path(args.output_dir) if args.output_dir else None
    print_report(
        generate_report(apk_path, aapt, output_dir, args.no_decompile, args.threads),
        args.json,
    )


if __name__ == "__main__":
    main()
