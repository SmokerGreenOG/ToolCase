"""Tests for dead_code_finder.py and todo_tracker.py."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
import tempfile
from pathlib import Path


class TestDeadCode(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cli_help(self):
        import subprocess
        from pathlib import Path as P
        tool = P(__file__).parent.parent / "dead_code_finder.py"
        r = subprocess.run([sys.executable, str(tool), "--help"],
                           capture_output=True, text=True)
        self.assertIn("usage", r.stdout.lower() + r.stderr.lower())


class TestTodoTracker(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finds_todo_marker(self):
        from todo_tracker import scan_file
        p = self.tmp / "test.py"
        p.write_text("# TODO: fix this\nprint('hi')\n", encoding="utf-8")
        results = list(scan_file(p, self.tmp))
        self.assertGreater(len(results), 0)
        self.assertTrue(any("TODO" in r.get("marker", "") for r in results))

    def test_finds_fixme(self):
        from todo_tracker import scan_file
        p = self.tmp / "test.py"
        p.write_text("# FIXME: broken\n", encoding="utf-8")
        results = list(scan_file(p, self.tmp))
        self.assertTrue(any("FIXME" in r.get("marker", "") for r in results))

    def test_finds_hack(self):
        from todo_tracker import scan_file
        p = self.tmp / "test.py"
        p.write_text("# HACK: workaround\n", encoding="utf-8")
        results = list(scan_file(p, self.tmp))
        self.assertTrue(any("HACK" in r.get("marker", "") for r in results))

    def test_clean_file_no_markers(self):
        from todo_tracker import scan_file
        p = self.tmp / "test.py"
        p.write_text("print('hi')\n", encoding="utf-8")
        results = list(scan_file(p, self.tmp))
        self.assertEqual(len(results), 0)

    def test_marker_words_inside_code_are_ignored(self):
        """Words such as template/debug are not TODO markers."""
        from todo_tracker import scan_file
        p = self.tmp / "clean.py"
        p.write_text(
            'template = "value"\n# one debug marker per line\n',
            encoding="utf-8",
        )
        self.assertEqual(list(scan_file(p, self.tmp)), [])


if __name__ == "__main__":
    unittest.main()
