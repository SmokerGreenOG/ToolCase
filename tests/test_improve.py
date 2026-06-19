"""Tests for improve.py — Main code analysis orchestrator."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile


class TestImproveCore(unittest.TestCase):
    """Test core functions from improve.py."""

    def setUp(self):
        """Create a temporary Python file for testing."""
        self.tmpdir = tempfile.mkdtemp()
        self.good_file = os.path.join(self.tmpdir, "good.py")
        with open(self.good_file, "w", encoding="utf-8") as f:
            f.write("def hello():\n    return 'world'\n")

        self.bad_file = os.path.join(self.tmpdir, "bad.py")
        with open(self.bad_file, "w", encoding="utf-8") as f:
            f.write("def broken(\n    pass\n")

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_syntax_check_good_file(self):
        """syntax_check should return True for valid Python."""
        from improve import syntax_check
        ok, msg = syntax_check(self.good_file)
        self.assertTrue(ok)
        self.assertEqual(msg, "Syntax OK")

    def test_syntax_check_bad_file(self):
        """syntax_check should return False for invalid Python."""
        from improve import syntax_check
        ok, msg = syntax_check(self.bad_file)
        self.assertFalse(ok)
        self.assertIn("SyntaxError", msg)

    def test_lint_check_no_issues(self):
        """lint_check should find no issues in clean code."""
        from improve import lint_check
        issues = lint_check(self.good_file)
        self.assertIsInstance(issues, list)

    def test_lint_check_long_line(self):
        """lint_check should flag lines > 100 chars."""
        from improve import lint_check
        long_line_file = os.path.join(self.tmpdir, "long.py")
        with open(long_line_file, "w", encoding="utf-8") as f:
            f.write("# " + "x" * 200 + "\n")
        issues = lint_check(long_line_file)
        self.assertTrue(any("E501" in i for i in issues),
                        f"Expected E501 in: {issues}")

    def test_analyze_file_existing(self):
        """analyze_file should return a report dict for existing files."""
        from improve import analyze_file
        report = analyze_file(self.good_file)
        self.assertIn("file", report)
        self.assertIn("syntax_ok", report)
        self.assertTrue(report["syntax_ok"])

    def test_analyze_file_nonexistent(self):
        """analyze_file should return error for missing files."""
        from improve import analyze_file
        report = analyze_file("/nonexistent/path.py")
        self.assertIn("error", report)
        self.assertIsNotNone(report["error"])

    def test_count_lines(self):
        """count_lines should return correct line count."""
        from improve import count_lines
        count = count_lines(self.good_file)
        self.assertEqual(count, 2)

    def test_find_python_files(self):
        """find_python_files should discover .py files."""
        from improve import find_python_files
        files = find_python_files(self.tmpdir)
        self.assertIsInstance(files, list)
        self.assertGreaterEqual(len(files), 1)

    def test_backup_file_creates_bak(self):
        """backup_file should create a .bak copy."""
        from improve import backup_file
        bak = backup_file(self.good_file)
        self.assertIsNotNone(bak)
        self.assertTrue(os.path.exists(bak))
        # Clean up
        os.remove(bak)


if __name__ == "__main__":
    unittest.main()
