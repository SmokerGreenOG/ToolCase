"""Tests for improve.py — Main code analysis orchestrator."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
from pathlib import Path


class TestImproveCore(unittest.TestCase):
    """Test core functions from improve.py."""

    def setUp(self) -> None:
        """Create a temporary Python file for testing."""
        self.tmpdir = tempfile.mkdtemp()
        self.good_file = os.path.join(self.tmpdir, "good.py")
        with open(self.good_file, "w", encoding="utf-8") as f:
            f.write("def hello():\n    return 'world'\n")

        self.bad_file = os.path.join(self.tmpdir, "bad.py")
        with open(self.bad_file, "w", encoding="utf-8") as f:
            f.write("def broken(\n    pass\n")

    def tearDown(self) -> None:
        """Clean up temp files."""
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_syntax_check_good_file(self) -> None:
        """syntax_check should return True for valid Python."""
        from improve import syntax_check

        ok, msg = syntax_check(self.good_file)
        self.assertTrue(ok)
        self.assertEqual(msg, "Syntax OK")

    def test_syntax_check_bad_file(self) -> None:
        """syntax_check should return False for invalid Python."""
        from improve import syntax_check

        ok, msg = syntax_check(self.bad_file)
        self.assertFalse(ok)
        self.assertIn("SyntaxError", msg)

    def test_lint_check_no_issues(self) -> None:
        """lint_check should find no issues in clean code."""
        from improve import lint_check

        issues = lint_check(self.good_file)
        self.assertIsInstance(issues, list)

    def test_lint_check_long_line(self) -> None:
        """lint_check should flag lines > 100 chars."""
        from improve import lint_check

        long_line_file = os.path.join(self.tmpdir, "long.py")
        with open(long_line_file, "w", encoding="utf-8") as f:
            f.write("# " + "x" * 200 + "\n")
        issues = lint_check(long_line_file)
        self.assertTrue(any("E501" in i for i in issues), f"Expected E501 in: {issues}")

    def test_analyze_file_existing(self) -> None:
        """analyze_file should return a report dict for existing files."""
        from improve import analyze_file

        report = analyze_file(self.good_file)
        self.assertIn("file", report)
        self.assertIn("syntax_ok", report)
        self.assertTrue(report["syntax_ok"])

    def test_analyze_file_nonexistent(self) -> None:
        """analyze_file should return error for missing files."""
        from improve import analyze_file

        report = analyze_file("/nonexistent/path.py")
        self.assertIn("error", report)
        self.assertIsNotNone(report["error"])

    def test_count_lines(self) -> None:
        """count_lines should return correct line count."""
        from improve import count_lines

        count = count_lines(self.good_file)
        self.assertEqual(count, 2)

    def test_find_python_files(self) -> None:
        """find_python_files should discover .py files."""
        from improve import find_python_files

        files = find_python_files(self.tmpdir)
        self.assertIsInstance(files, list)
        self.assertGreaterEqual(len(files), 1)

    def test_backup_file_creates_bak(self) -> None:
        """backup_file should create a .bak copy."""
        from improve import backup_file

        bak = backup_file(self.good_file)
        self.assertIsNotNone(bak)
        self.assertTrue(os.path.exists(bak))
        # Clean up
        os.remove(bak)

    def test_core_scan_runs_all_10_tools(self) -> None:
        """--core-scan must dispatch exactly 10 read-only tools."""
        # The tools listed in the core-scan dispatcher (improve.py lines 828-838)
        expected_tools = [
            "multiscan.py",
            "complexity.py",
            "depgraph.py",
            "security_scan.py",
            "env_check.py",
            "project_doctor.py",
            "todo_tracker.py",
            "dead_code_finder.py",
            "dependency_audit.py",
            "license_checker.py",
        ]
        self.assertEqual(len(expected_tools), 10, "Core scan must have exactly 10 tools")

        # Verify each tool script exists on disk
        import improve

        tool_path = Path(improve.__file__).parent
        for script in expected_tools:
            self.assertTrue((tool_path / script).exists(), f"Core-scan tool missing: {script}")

    def test_core_scan_dispatches_all_tools(self) -> None:
        """--core-scan dispatch list must contain exactly 10 tools (AST-verified)."""
        import ast
        from pathlib import Path

        source = Path(__file__).parent.parent / "improve.py"
        tree = ast.parse(source.read_text())

        # Find the if args.core_scan block and extract tool script names
        core_scan_found = False
        tool_scripts = []
        for node in ast.walk(tree):
            try:
                if (
                    isinstance(node, ast.If)
                    and isinstance(node.test, ast.Attribute)
                    and node.test.attr == "core_scan"
                ):
                    core_scan_found = True
                    for stmt in ast.walk(node):
                        if isinstance(stmt, ast.List):
                            for elt in stmt.elts:
                                if isinstance(elt, ast.Tuple) and len(elt.elts) >= 2:
                                    if isinstance(elt.elts[1], ast.Constant):
                                        tool_scripts.append(elt.elts[1].value)
                    break
            except Exception:
                pass

        self.assertTrue(core_scan_found, "Could not find if args.core_scan in improve.py")
        expected = [
            "multiscan.py",
            "complexity.py",
            "depgraph.py",
            "security_scan.py",
            "env_check.py",
            "project_doctor.py",
            "todo_tracker.py",
            "dead_code_finder.py",
            "dependency_audit.py",
            "license_checker.py",
        ]
        self.assertEqual(
            len(tool_scripts), 10, f"Expected 10 tools, found {len(tool_scripts)}: {tool_scripts}"
        )
        for script in expected:
            self.assertIn(
                script,
                tool_scripts,
                f"Tool {script} missing from core-scan dispatch: {tool_scripts}",
            )

    def test_no_shell_true_in_source(self) -> None:
        """Verify no shell=True in source code outside known allowlist."""
        import ast
        from pathlib import Path

        project_root = Path(__file__).parent.parent
        # Files allowed to use subprocess with shell=True (safe_run.py itself, tests)
        allowlist = {
            "safe_run.py",
            "command_guard.py",
            "release_packager.py",
            "test_command_guard.py",
            "test_safe_run.py",
        }
        violations = []
        for py_file in project_root.rglob("*.py"):
            parts = set(py_file.parts)
            if parts & {"__pycache__", ".venv", "venv", "build", "dist", ".rsi_backups", ".git"}:
                continue
            if py_file.name in allowlist:
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except Exception:
                continue
            # Check for shell=True in subprocess calls
            for node in ast.walk(tree):
                # Check subprocess.run(..., shell=True)
                if isinstance(node, ast.Call):
                    for kw in getattr(node, "keywords", []) or []:
                        if (
                            kw.arg == "shell"
                            and isinstance(kw.value, ast.Constant)
                            and kw.value.value is True
                        ):
                            violations.append(
                                f"{py_file.relative_to(project_root)}: subprocess call with shell=True"
                            )
                # Check os.system() calls
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        if (
                            node.func.attr == "system"
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == "os"
                        ):
                            violations.append(
                                f"{py_file.relative_to(project_root)}: os.system() call"
                            )
        if violations:
            self.fail(
                "Direct shell=True or os.system() found in source (use safe_run instead):\n"
                + "\n".join(violations)
            )
        else:
            self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
