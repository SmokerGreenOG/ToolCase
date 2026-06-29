from __future__ import annotations

__maker__ = "SmokerGreenOG"
import _protect

import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from apk_reverse_suite.core.engine import analyze_apk
from apk_reverse_suite.core.scanner import (
    extract_apk,
    file_hashes,
    parse_manifest_text,
    scan_bytes,
)
from apk_reverse_suite.core.utils import run_command


class ApkReverseSuiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_apk(self, name: str = "sample.apk") -> Path:
        apk = self.root / name
        manifest = (
            '<manifest package="com.example.app" '
            'xmlns:android="http://schemas.android.com/apk/res/android">'
            '<uses-permission android:name="android.permission.CAMERA"/>'
            '<application><activity android:name=".MainActivity"/></application>'
            '</manifest>'
        )
        with zipfile.ZipFile(apk, "w") as archive:
            archive.writestr("AndroidManifest.xml", manifest)
            archive.writestr(
                "classes.dex",
                b'https://api.example.com/v1 api_key="ABCDEFGHIJKLMNOPQRSTUV" '
                b"Runtime.getRuntime",
            )
            archive.writestr("lib/arm64-v8a/libflutter.so", b"ELF")
        return apk

    def test_end_to_end_analysis_and_repeatable_output(self) -> None:
        apk = self.make_apk()
        out = self.root / "report"
        result = analyze_apk(apk, out)

        self.assertEqual(result["manifest"]["package"], "com.example.app")
        self.assertIn("android.permission.CAMERA", result["manifest"]["suspicious_permissions"])
        self.assertIn("Flutter", result["frameworks"])
        self.assertIn("https://api.example.com/v1", result["scan"]["urls"])
        self.assertTrue(Path(result["artifacts"]["json_report"]).is_file())
        self.assertTrue(Path(result["artifacts"]["html_report"]).is_file())
        json.loads(Path(result["artifacts"]["json_report"]).read_text(encoding="utf-8"))

        stale = out / "extracted" / "stale.txt"
        stale.write_text("from an earlier run", encoding="utf-8")
        old_jadx = out / "jadx"
        old_jadx.mkdir()
        (old_jadx / "stale.java").write_text("old", encoding="utf-8")
        analyze_apk(apk, out)
        self.assertFalse(stale.exists())
        self.assertFalse(old_jadx.exists())

    def test_urls_and_secrets_are_detected_without_exposing_secret(self) -> None:
        raw_secret = "ABCDEFGHIJKLMNOPQRSTUV"
        result = scan_bytes(f'https://example.test/a api_key="{raw_secret}"'.encode())
        self.assertEqual(result["urls"], ["https://example.test/a"])
        self.assertEqual(len(result["secrets"]), 1)
        self.assertIn("generic_token: sha256:", result["secrets"][0])
        self.assertNotIn(raw_secret, result["secrets"][0])

    def test_parent_path_is_rejected(self) -> None:
        apk = self.root / "unsafe.apk"
        with zipfile.ZipFile(apk, "w") as archive:
            archive.writestr("../escape.txt", "no")
        with self.assertRaisesRegex(ValueError, "Unsafe APK entry path"):
            extract_apk(apk, self.root / "out")
        self.assertFalse((self.root / "escape.txt").exists())

    def test_symlink_is_rejected(self) -> None:
        apk = self.root / "symlink.apk"
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(apk, "w") as archive:
            archive.writestr(info, "target")
        with self.assertRaisesRegex(ValueError, "Symbolic links"):
            extract_apk(apk, self.root / "out")

    def test_expanded_size_limit_is_enforced(self) -> None:
        apk = self.root / "large.apk"
        with zipfile.ZipFile(apk, "w") as archive:
            archive.writestr("large.bin", b"x" * 32)
        with self.assertRaisesRegex(ValueError, "too large"):
            extract_apk(apk, self.root / "out", max_file_bytes=16)

    def test_foreign_output_is_not_overwritten(self) -> None:
        apk = self.make_apk()
        foreign = self.root / "report" / "extracted"
        foreign.mkdir(parents=True)
        keep = foreign / "keep.txt"
        keep.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
            analyze_apk(apk, self.root / "report")
        self.assertEqual(keep.read_text(encoding="utf-8"), "keep")

    def test_invalid_apk_does_not_destroy_previous_output(self) -> None:
        out = self.root / "report"
        analyze_apk(self.make_apk(), out)
        keep = out / "extracted" / "keep.txt"
        keep.write_text("keep", encoding="utf-8")
        invalid = self.root / "invalid.apk"
        invalid.write_text("not a zip archive", encoding="utf-8")
        with self.assertRaises(zipfile.BadZipFile):
            analyze_apk(invalid, out)
        self.assertEqual(keep.read_text(encoding="utf-8"), "keep")

    def test_binary_manifest_candidate_is_skipped_for_decoded_xml(self) -> None:
        raw = self.root / "raw"
        decoded = self.root / "decoded"
        raw.mkdir()
        decoded.mkdir()
        (raw / "AndroidManifest.xml").write_bytes(b"\x03\x00manifest\x00binary")
        (decoded / "AndroidManifest.xml").write_text(
            '<manifest package="com.decoded.app" '
            'xmlns:android="http://schemas.android.com/apk/res/android">'
            '<uses-permission android:name="android.permission.READ_SMS"/>'
            '</manifest>',
            encoding="utf-8",
        )
        result = parse_manifest_text([raw, decoded])
        self.assertEqual(result["package"], "com.decoded.app")
        self.assertEqual(result["permissions"], ["android.permission.READ_SMS"])

    def test_file_hash_limit_counts_files_not_directories(self) -> None:
        (self.root / "a" / "b" / "c").mkdir(parents=True)
        (self.root / "a" / "b" / "c" / "one.txt").write_text("1", encoding="utf-8")
        (self.root / "two.txt").write_text("2", encoding="utf-8")
        self.assertEqual(len(file_hashes(self.root, limit=1)), 1)

    def test_missing_command_returns_structured_error(self) -> None:
        result = run_command(["command-that-does-not-exist-toolcase-apk-suite"])
        self.assertEqual(result["returncode"], -1)
        self.assertTrue(
            result.get("stderr", "") != "",
            f"Expected non-empty stderr for missing command, got: {result}",
        )


if __name__ == "__main__":
    unittest.main()
