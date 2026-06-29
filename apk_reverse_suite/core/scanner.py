from __future__ import annotations

__maker__ = "SmokerGreenOG"
import _protect

import hashlib
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree

from .patterns import (
    EMAIL_RE,
    IP_RE,
    PACKAGE_RE,
    RISKY_STRINGS,
    SECRET_PATTERNS,
    SUSPICIOUS_PERMISSIONS,
    URL_RE,
)
from .utils import safe_relpath, sha256_file

TEXT_EXTS = {
    ".xml", ".json", ".txt", ".html", ".js", ".properties",
    ".cfg", ".ini", ".yml", ".yaml",
}

DEFAULT_MAX_ENTRIES = 100_000
DEFAULT_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_FILE_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_COMPRESSION_RATIO = 1_000
ANDROID_XML_NAMESPACE = "http://schemas.android.com/apk/res/android"


def apk_inventory(apk_path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with zipfile.ZipFile(apk_path, "r") as zf:
        for info in zf.infolist():
            items.append({
                "path": info.filename,
                "compressed_size": info.compress_size,
                "size": info.file_size,
                "is_dir": info.is_dir(),
            })
    return items


def _validated_members(
    zf: zipfile.ZipFile,
    extract_dir: Path,
    *,
    max_entries: int,
    max_total_bytes: int,
    max_file_bytes: int,
    max_compression_ratio: int,
) -> list[tuple[zipfile.ZipInfo, Path]]:
    infos = zf.infolist()
    if len(infos) > max_entries:
        raise ValueError(f"APK contains too many entries: {len(infos)} > {max_entries}")

    root = extract_dir.resolve()
    total_bytes = 0
    seen: set[str] = set()
    validated: list[tuple[zipfile.ZipInfo, Path]] = []

    for info in infos:
        name = info.filename.replace("\\", "/")
        relative = PurePosixPath(name)
        if not name or relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe APK entry path: {info.filename!r}")
        if any(":" in part or part in {"", "."} for part in relative.parts):
            raise ValueError(f"Unsafe APK entry path: {info.filename!r}")

        normalized = "/".join(relative.parts).casefold()
        if normalized in seen:
            raise ValueError(f"Duplicate APK entry path: {info.filename!r}")
        seen.add(normalized)

        unix_mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(unix_mode):
            raise ValueError(f"Symbolic links are not allowed in APKs: {info.filename!r}")
        if info.flag_bits & 0x1:
            raise ValueError(f"Encrypted APK entry is not supported: {info.filename!r}")
        if info.file_size > max_file_bytes:
            raise ValueError(
                f"APK entry is too large: {info.filename!r} "
                f"({info.file_size} > {max_file_bytes} bytes)"
            )

        total_bytes += info.file_size
        if total_bytes > max_total_bytes:
            raise ValueError(
                f"APK expands beyond the safety limit: "
                f"{total_bytes} > {max_total_bytes} bytes"
            )
        if info.file_size and not info.is_dir():
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > max_compression_ratio:
                raise ValueError(
                    f"Suspicious compression ratio for {info.filename!r}: {ratio:.0f}:1"
                )

        target = root.joinpath(*relative.parts).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"APK entry escapes the output directory: {info.filename!r}")
        validated.append((info, target))

    return validated


def extract_apk(
    apk_path: Path,
    extract_dir: Path,
    *,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_compression_ratio: int = DEFAULT_MAX_COMPRESSION_RATIO,
) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk_path, "r") as zf:
        members = _validated_members(
            zf,
            extract_dir,
            max_entries=max_entries,
            max_total_bytes=max_total_bytes,
            max_file_bytes=max_file_bytes,
            max_compression_ratio=max_compression_ratio,
        )
        for info, target in members:
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as source, target.open("xb") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)


def validate_apk(
    apk_path: Path,
    extract_dir: Path,
    *,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_compression_ratio: int = DEFAULT_MAX_COMPRESSION_RATIO,
) -> None:
    """Validate all archive members without writing extracted content."""
    with zipfile.ZipFile(apk_path, "r") as zf:
        _validated_members(
            zf,
            extract_dir,
            max_entries=max_entries,
            max_total_bytes=max_total_bytes,
            max_file_bytes=max_file_bytes,
            max_compression_ratio=max_compression_ratio,
        )


def detect_frameworks(inventory: list[dict[str, Any]]) -> list[str]:
    paths = [i["path"] for i in inventory]
    joined = "\n".join(paths).lower()
    found = []
    if "libflutter.so" in joined or "flutter_assets" in joined:
        found.append("Flutter")
    if "libunity.so" in joined or "assets/bin/data" in joined:
        found.append("Unity")
    if "index.android.bundle" in joined or "reactnative" in joined:
        found.append("React Native")
    if "cordova.js" in joined or "www/" in joined:
        found.append("Cordova/WebView")
    if "mono/" in joined or "libmonodroid" in joined:
        found.append("Xamarin/.NET")
    if "kotlin/" in joined or "kotlinx" in joined:
        found.append("Kotlin")
    if any(p.startswith("lib/") and p.endswith(".so") for p in paths):
        found.append("Native libraries")
    return sorted(set(found))


def scan_bytes(data: bytes) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {
        "urls": [],
        "ips": [],
        "emails": [],
        "packages": [],
        "secrets": [],
        "risky_strings": [],
    }
    basic_patterns = [
        ("urls", URL_RE),
        ("ips", IP_RE),
        ("emails", EMAIL_RE),
        ("packages", PACKAGE_RE),
    ]
    for key, regex in basic_patterns:
        out[key] = sorted({m.decode("utf-8", "ignore")[:500] for m in regex.findall(data)})[:200]
    secrets = []
    for name, regex in SECRET_PATTERNS.items():
        for match in regex.finditer(data):
            fingerprint = hashlib.sha256(match.group(0)).hexdigest()[:12]
            secrets.append(f"{name}: sha256:{fingerprint}")
    out["secrets"] = sorted(set(secrets))[:100]
    risky = []
    for marker in RISKY_STRINGS:
        if marker in data:
            risky.append(marker.decode("utf-8", "ignore"))
    out["risky_strings"] = sorted(set(risky))
    return out


def scan_extracted_tree(root: Path, max_file_mb: int = 20) -> dict[str, Any]:
    aggregate: dict[str, Any] = {
        "files_scanned": 0,
        "urls": [],
        "ips": [],
        "emails": [],
        "packages": [],
        "secrets": [],
        "risky_strings": [],
        "dex_files": [],
        "native_libs": [],
        "cert_files": [],
        "manifest_candidates": [],
    }
    max_bytes = max_file_mb * 1024 * 1024
    for path in sorted(root.rglob("*"), key=lambda item: str(item).casefold()):
        if not path.is_file():
            continue
        rel = safe_relpath(path, root)
        lower = rel.lower()
        if lower.endswith(".dex"):
            aggregate["dex_files"].append(rel)
        if lower.endswith(".so"):
            aggregate["native_libs"].append(rel)
        if lower.endswith((".rsa", ".dsa", ".ec", ".sf", ".mf", ".pem", ".crt", ".cer")):
            aggregate["cert_files"].append(rel)
        if rel.endswith("AndroidManifest.xml"):
            aggregate["manifest_candidates"].append(rel)
        if path.stat().st_size > max_bytes:
            continue
        suffix = path.suffix.lower()
        should_scan = (
            suffix in TEXT_EXTS
            or suffix in {".dex", ".so"}
            or path.stat().st_size < 2_000_000
        )
        if not should_scan:
            continue
        data = path.read_bytes()
        found = scan_bytes(data)
        aggregate["files_scanned"] += 1
        for key in ["urls", "ips", "emails", "packages", "risky_strings"]:
            aggregate[key].extend(found[key])
        aggregate["secrets"].extend(f"{rel}: {value}" for value in found["secrets"])
    result_keys = [
        "urls", "ips", "emails", "packages", "secrets", "risky_strings",
        "dex_files", "native_libs", "cert_files", "manifest_candidates",
    ]
    for key in result_keys:
        aggregate[key] = sorted(set(aggregate[key]))[:500]
    return aggregate


def parse_manifest_text(decoded_dirs: list[Path]) -> dict[str, Any]:
    result = {"permissions": [], "components": [], "package": None, "raw_source": None}
    candidates: list[Path] = []
    for d in decoded_dirs:
        candidates.extend(sorted(d.rglob("AndroidManifest.xml")))
    for manifest in candidates:
        try:
            if manifest.stat().st_size > 10 * 1024 * 1024:
                continue
            root = ElementTree.fromstring(manifest.read_bytes())
        except (OSError, ElementTree.ParseError, ValueError):
            continue
        if root.tag.rsplit("}", 1)[-1] != "manifest":
            continue

        result["raw_source"] = str(manifest)
        result["package"] = root.attrib.get("package")
        android_name = f"{{{ANDROID_XML_NAMESPACE}}}name"
        permissions: set[str] = set()
        components: set[str] = set()
        component_tags = {"activity", "activity-alias", "service", "receiver", "provider"}
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            name = element.attrib.get(android_name) or element.attrib.get("android:name")
            if tag.startswith("uses-permission") and name:
                permissions.add(name)
            if tag in component_tags and name:
                components.add(f"{tag}: {name}")
        result["permissions"] = sorted(permissions)
        result["components"] = sorted(components)
        break
    result["suspicious_permissions"] = sorted(set(result["permissions"]) & SUSPICIOUS_PERMISSIONS)
    return result


def file_hashes(root: Path, limit: int = 3000) -> list[dict[str, str]]:
    rows = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item).casefold()):
        if path.is_file():
            rows.append({"path": safe_relpath(path, root), "sha256": sha256_file(path)})
            if len(rows) >= limit:
                break
    return rows
