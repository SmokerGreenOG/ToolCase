"""Tests for self_improve_loop.py — Core data classes and safety."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from pathlib import Path
from datetime import datetime


class TestSelfImproveCore(unittest.TestCase):
    """Test core components of self_improve_loop.py."""

    def test_finding_dataclass(self):
        """Finding dataclass should create instances."""
        from self_improve_loop import Finding
        f = Finding(
            category="code-quality",
            severity="high",
            message="Test finding",
            file="test.py",
            line=42,
            suggestion="Fix it",
        )
        self.assertEqual(f.category, "code-quality")
        self.assertEqual(f.severity, "high")
        self.assertEqual(f.message, "Test finding")
        self.assertEqual(f.file, "test.py")
        self.assertEqual(f.line, 42)
        self.assertEqual(f.suggestion, "Fix it")

    def test_change_dataclass(self):
        """Change dataclass should create instances."""
        from self_improve_loop import Change
        c = Change(
            description="Test change",
            category="safe",
            file="test.py",
            reason="Auto-fixable",
        )
        self.assertEqual(c.description, "Test change")
        self.assertEqual(c.category, "safe")
        self.assertEqual(c.status, "planned")

    def test_cycle_report_defaults(self):
        """CycleReport should have sensible defaults."""
        from self_improve_loop import CycleReport
        r = CycleReport(cycle=1, mode="dry-run", focus="all")
        self.assertEqual(r.cycle, 1)
        self.assertEqual(r.mode, "dry-run")
        self.assertEqual(r.findings, [])
        self.assertEqual(r.planned_improvements, [])
        self.assertEqual(r.tests["status"], "not_run")
        self.assertFalse(r.rollback["executed"])
        self.assertEqual(r.status, "passed")

    def test_cycle_report_exit_code_passed(self):
        """Passed status should return exit code 0."""
        from self_improve_loop import CycleReport
        r = CycleReport(cycle=1, mode="dry-run", focus="all", status="passed")
        self.assertEqual(r.final_exit_code(), 0)

    def test_cycle_report_exit_code_warning(self):
        """Warning status should return exit code 1."""
        from self_improve_loop import CycleReport
        r = CycleReport(cycle=1, mode="dry-run", focus="all", status="warning")
        self.assertEqual(r.final_exit_code(), 1)

    def test_cycle_report_exit_code_failed(self):
        """Failed status should return exit code 2."""
        from self_improve_loop import CycleReport
        r = CycleReport(cycle=1, mode="dry-run", focus="all", status="failed")
        self.assertEqual(r.final_exit_code(), 2)

    def test_cycle_report_exit_code_rolled_back(self):
        """Rolled back status should return exit code 3."""
        from self_improve_loop import CycleReport
        r = CycleReport(cycle=1, mode="dry-run", focus="all",
                         status="rolled_back")
        self.assertEqual(r.final_exit_code(), 3)

    def test_cycle_report_exit_code_blocked(self):
        """Blocked status should return exit code 4."""
        from self_improve_loop import CycleReport
        r = CycleReport(cycle=1, mode="dry-run", focus="all", status="blocked")
        self.assertEqual(r.final_exit_code(), 4)

    def test_safety_manager_forbidden_commands(self):
        """SafetyManager should block rm -rf."""
        from self_improve_loop import SafetyManager
        sm = SafetyManager(Path("."))
        result = sm.is_command_forbidden("rm -rf /")
        self.assertIsNotNone(result)
        self.assertIn("forbidden", result.lower())

    def test_safety_manager_safe_commands(self):
        """SafetyManager should allow safe commands."""
        from self_improve_loop import SafetyManager
        sm = SafetyManager(Path("."))
        result = sm.is_command_forbidden("python --version")
        self.assertIsNone(result)

    def test_safety_manager_forbidden_reads(self):
        """SafetyManager should block .env reads."""
        from self_improve_loop import SafetyManager
        sm = SafetyManager(Path("."))
        result = sm.is_file_forbidden_to_read(".env")
        self.assertIsNotNone(result)

    def test_safety_manager_safe_reads(self):
        """SafetyManager should allow non-sensitive file reads."""
        from self_improve_loop import SafetyManager
        sm = SafetyManager(Path("."))
        result = sm.is_file_forbidden_to_read("test.py")
        self.assertIsNone(result)

    def test_safety_manager_within_workspace(self):
        """SafetyManager should accept paths within workspace."""
        from self_improve_loop import SafetyManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            sm = SafetyManager(Path(tmp))
            inner = Path(tmp) / "test.py"
            inner.write_text("x=1")
            result = sm.within_workspace(inner)
            self.assertEqual(result, inner)

    def test_safety_manager_outside_workspace_blocked(self):
        """SafetyManager should block paths outside workspace."""
        from self_improve_loop import SafetyManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            sm = SafetyManager(Path(tmp))
            with self.assertRaises(PermissionError):
                sm.within_workspace(Path(tempfile.gettempdir()) / "secret.txt")

    def test_safety_manager_create_backup(self):
        """SafetyManager.create_backup should create .bak files."""
        from self_improve_loop import SafetyManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            test_file = tmp_path / "test.py"
            test_file.write_text("x=1")
            sm = SafetyManager(tmp_path)
            bak = sm.create_backup(test_file)
            self.assertIsNotNone(bak)
            bak_path = Path(bak)
            self.assertTrue(bak_path.exists())
            # Cleanup
            import shutil
            shutil.rmtree(tmp_path / ".backups", ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
