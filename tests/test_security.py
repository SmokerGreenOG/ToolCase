"""Tests for security_scan.py — Security vulnerability scanner."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile


class TestSecurityScan(unittest.TestCase):
    """Test security scanning functionality."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scan_clean_file_no_findings(self):
        """A clean file should have no security findings."""
        from security_scan import scan_file
        from pathlib import Path
        clean = os.path.join(self.tmpdir, "clean.py")
        with open(clean, "w", encoding="utf-8") as f:
            f.write("import os\nprint('hello')\n")
        findings = scan_file(Path(clean))
        self.assertEqual(len(findings), 0)

    def test_scan_detects_api_key(self):
        """A file with an API key should be flagged."""
        from security_scan import scan_file
        from pathlib import Path
        risky = os.path.join(self.tmpdir, "risky.py")
        with open(risky, "w", encoding="utf-8") as f:
            f.write('API_KEY = "sk-1234567890abcdef"\n')
        findings = scan_file(Path(risky))
        self.assertGreater(len(findings), 0)
        self.assertTrue(any(f["risk"] == "HIGH" for f in findings))

    def test_scan_detects_eval(self):
        """A file with eval() should be flagged."""
        from security_scan import scan_file
        from pathlib import Path
        risky = os.path.join(self.tmpdir, "eval_risk.py")
        with open(risky, "w", encoding="utf-8") as f:
            f.write('eval("print(1)")\n')
        findings = scan_file(Path(risky))
        self.assertGreater(len(findings), 0)
        self.assertTrue(any(f["pattern"] == "eval_exec" for f in findings))

    def test_scan_detects_private_key(self):
        """A file with a private key header should be flagged."""
        from security_scan import scan_file
        from pathlib import Path
        risky = os.path.join(self.tmpdir, "key.pem")
        with open(risky, "w", encoding="utf-8") as f:
            f.write("-----BEGIN RSA PRIVATE KEY-----\n")
        findings = scan_file(Path(risky))
        self.assertGreater(len(findings), 0)
        self.assertTrue(any(f["pattern"] == "private_key" for f in findings))

    def test_collect_files_finds_py(self):
        """collect_files should find .py files."""
        from security_scan import collect_files
        from pathlib import Path
        # Create a file
        test_file = os.path.join(self.tmpdir, "test.py")
        with open(test_file, "w") as f:
            f.write("x = 1\n")
        files = collect_files(Path(self.tmpdir))
        self.assertGreater(len(files), 0)
        self.assertTrue(any(f.name == "test.py" for f in files))

    def test_mask_secret(self):
        """_mask_secret should mask sensitive values."""
        from security_scan import _mask_secret
        masked = _mask_secret('API_KEY = "sk-1234567890abcdef"')
        self.assertIn("**", masked)
        self.assertNotIn("1234567890abcdef", masked.replace("****", ""))

    def test_scan_exclude_binary_extensions(self):
        """Binary files should be skipped."""
        from security_scan import scan_file
        from pathlib import Path
        binary = os.path.join(self.tmpdir, "file.png")
        with open(binary, "wb") as f:
            f.write(b"PNG\x0d\x0a\x1a\x0a")
        findings = scan_file(Path(binary))
        self.assertEqual(len(findings), 0)

    def test_scan_detects_connection_string(self):
        """Connection strings with credentials should be flagged."""
        from security_scan import scan_file
        from pathlib import Path
        risky = os.path.join(self.tmpdir, "config.py")
        with open(risky, "w", encoding="utf-8") as f:
            f.write('DB = "postgresql://user:pass123@localhost:5432/db"\n')
        findings = scan_file(Path(risky))
        self.assertGreater(len(findings), 0)
        self.assertTrue(any(f["pattern"] == "connection_string" for f in findings))


if __name__ == "__main__":
    unittest.main()
