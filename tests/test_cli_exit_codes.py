"""Tests for improve.py CLI exit codes — verifies machine-readable exit codes.

Exit code contract:
  0 (EXIT_OK):       Success, no issues found
  1 (EXIT_FINDINGS): Issues/findings detected
  2 (EXIT_ERROR):    Invalid input, syntax/internal error
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
import subprocess
from pathlib import Path


IMPROVE_PY = Path(__file__).resolve().parent.parent / "improve.py"


def _run_improve(*args: str) -> subprocess.CompletedProcess:
    """Run improve.py with given args and return the result."""
    return subprocess.run(
        [sys.executable, str(IMPROVE_PY)] + list(args),
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestImproveExitCodes(unittest.TestCase):
    """Test that improve.py returns correct exit codes for all scenarios."""

    def setUp(self) -> None:
        """Create temp directory with test files."""
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        """Clean up."""
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ── Error cases (exit 2) ───────────────────────────────

    def test_nonexistent_file_returns_2(self) -> None:
        """File does not exist → exit 2."""
        result = _run_improve(os.path.join(self.tmpdir, "nonexistent.py"))
        self.assertEqual(result.returncode, 2, f"Expected exit 2, got {result.returncode}")

    def test_non_python_file_returns_2(self) -> None:
        """File is not a .py file → exit 2."""
        txt_file = os.path.join(self.tmpdir, "readme.txt")
        with open(txt_file, "w") as f:
            f.write("Not Python")
        result = _run_improve(txt_file)
        self.assertEqual(result.returncode, 2, f"Expected exit 2, got {result.returncode}")

    def test_empty_directory_returns_2(self) -> None:
        """Directory with no Python files → exit 2."""
        empty_dir = os.path.join(self.tmpdir, "empty")
        os.makedirs(empty_dir)
        result = _run_improve(empty_dir)
        self.assertEqual(result.returncode, 2, f"Expected exit 2, got {result.returncode}")

    def test_no_args_returns_2(self) -> None:
        """No target and no flags → exit 2 (error)."""
        result = _run_improve()
        self.assertEqual(result.returncode, 2, f"Expected exit 2, got {result.returncode}")

    # ── Success (exit 0) ───────────────────────────────────

    def test_clean_python_file_returns_0(self) -> None:
        """Clean Python file → exit 0."""
        clean_file = os.path.join(self.tmpdir, "clean.py")
        with open(clean_file, "w", encoding="utf-8") as f:
            f.write("def hello():\n    return 'world'\n")
        result = _run_improve(clean_file)
        self.assertEqual(result.returncode, 0, f"Expected exit 0, got {result.returncode}")

    def test_list_tools_returns_0(self) -> None:
        """--list-tools is informational → exit 0."""
        result = _run_improve("--list-tools")
        self.assertEqual(result.returncode, 0, f"Expected exit 0, got {result.returncode}")

    # ── Findings (exit 1) ──────────────────────────────────

    def test_syntax_error_returns_1(self) -> None:
        """Python file with syntax error → exit 1 (findings)."""
        bad_file = os.path.join(self.tmpdir, "bad.py")
        with open(bad_file, "w", encoding="utf-8") as f:
            f.write("def broken(\n    pass\n")
        result = _run_improve(bad_file)
        self.assertEqual(result.returncode, 1, f"Expected exit 1, got {result.returncode}")

    def test_todo_finding_returns_1(self) -> None:
        """Python file with TODO → exit 1 (findings)."""
        todo_file = os.path.join(self.tmpdir, "todo.py")
        with open(todo_file, "w", encoding="utf-8") as f:
            f.write("# TODO: fix this\nprint('hello')\n")
        result = _run_improve(todo_file)
        self.assertEqual(result.returncode, 1, f"Expected exit 1, got {result.returncode}")

    def test_long_line_returns_1(self) -> None:
        """Python file with E501 → exit 1."""
        long_file = os.path.join(self.tmpdir, "long.py")
        with open(long_file, "w", encoding="utf-8") as f:
            f.write("# " + "x" * 200 + "\n")
        result = _run_improve(long_file)
        self.assertEqual(result.returncode, 1, f"Expected exit 1, got {result.returncode}")

    def test_snippet_with_todo_returns_1(self) -> None:
        """--code with TODO → exit 1."""
        result = _run_improve("--code", "# TODO: fix\nprint('x')")
        self.assertEqual(result.returncode, 1, f"Expected exit 1, got {result.returncode}")

    def test_directory_with_issues_returns_1(self) -> None:
        """Directory with Python files containing issues → exit 1."""
        subdir = os.path.join(self.tmpdir, "src")
        os.makedirs(subdir)
        clean_file = os.path.join(subdir, "clean.py")
        with open(clean_file, "w", encoding="utf-8") as f:
            f.write("def hello():\n    return 'world'\n")
        todo_file = os.path.join(subdir, "todo.py")
        with open(todo_file, "w", encoding="utf-8") as f:
            f.write("# TODO: fix\nprint('x')\n")
        result = _run_improve(subdir, "--recursive")
        self.assertEqual(result.returncode, 1, f"Expected exit 1, got {result.returncode}")


if __name__ == "__main__":
    unittest.main()
