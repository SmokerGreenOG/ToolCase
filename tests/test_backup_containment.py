"""Tests for backup_manager.py workspace containment and --force enforcement.

Verifies:
  - External paths are rejected (snapshot, restore-file, diff, list)
  - Destructive operations require --force
  - In-workspace operations succeed
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
import subprocess
from pathlib import Path


BACKUP_MGR = Path(__file__).resolve().parent.parent / "backup_manager.py"


def _run_backup(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run backup_manager.py with given args."""
    return subprocess.run(
        [sys.executable, str(BACKUP_MGR)] + list(args),
        capture_output=True,
        text=True,
        timeout=30,
        cwd=cwd,
    )


class TestBackupManagerWorkspaceContainment(unittest.TestCase):
    """Test that backup_manager enforces workspace boundaries."""

    def setUp(self) -> None:
        """Create workspace directory."""
        self.workspace = tempfile.mkdtemp()
        # Create a file inside workspace
        self.inside_file = os.path.join(self.workspace, "test.py")
        with open(self.inside_file, "w") as f:
            f.write("print('hello')\n")
        # Create a file outside workspace
        self.outside_dir = tempfile.mkdtemp()
        self.outside_file = os.path.join(self.outside_dir, "outside.py")
        with open(self.outside_file, "w") as f:
            f.write("print('outside')\n")

    def tearDown(self) -> None:
        """Clean up."""
        import shutil
        shutil.rmtree(self.workspace, ignore_errors=True)
        shutil.rmtree(self.outside_dir, ignore_errors=True)

    # ── Workspace boundary: snapshot ───────────────────────

    def test_snapshot_inside_workspace_succeeds(self) -> None:
        """Snapshot of file inside workspace → succeeds."""
        result = _run_backup("--json", "snapshot", "test.py", cwd=self.workspace)
        self.assertEqual(result.returncode, 0,
                         f"Expected exit 0, got {result.returncode}: {result.stderr}")
        self.assertIn('"status": "ok"', result.stdout)

    def test_snapshot_outside_workspace_rejected(self) -> None:
        """Snapshot of file outside workspace → rejected."""
        result = _run_backup("--json", "snapshot", self.outside_file,
                             cwd=self.workspace)
        self.assertEqual(result.returncode, 2,
                         f"Expected exit 2, got {result.returncode}")
        self.assertIn("outside workspace", result.stdout)

    # ── Workspace boundary: restore-file ───────────────────

    def test_restore_file_outside_workspace_rejected(self) -> None:
        """Restore-file with external path → rejected."""
        result = _run_backup(
            "--json", "restore-file", "2026-01-01-000000", self.outside_file,
            "--force", cwd=self.workspace,
        )
        self.assertEqual(result.returncode, 2,
                         f"Expected exit 2, got {result.returncode}")
        self.assertIn("outside workspace", result.stdout)

    # ── --force enforcement ────────────────────────────────

    def test_restore_without_force_rejected(self) -> None:
        """Restore without --force → rejected."""
        result = _run_backup("--json", "restore", "2026-01-01-000000",
                             cwd=self.workspace)
        self.assertEqual(result.returncode, 2,
                         f"Expected exit 2, got {result.returncode}")
        self.assertIn("requires --force", result.stdout)

    def test_restore_file_without_force_rejected(self) -> None:
        """Restore-file without --force → rejected."""
        result = _run_backup(
            "--json", "restore-file", "2026-01-01-000000", "test.py",
            cwd=self.workspace,
        )
        self.assertEqual(result.returncode, 2,
                         f"Expected exit 2, got {result.returncode}")
        self.assertIn("requires --force", result.stdout)

    def test_prune_without_force_rejected(self) -> None:
        """Prune without --force → rejected."""
        result = _run_backup("--json", "prune", cwd=self.workspace)
        self.assertEqual(result.returncode, 2,
                         f"Expected exit 2, got {result.returncode}")
        self.assertIn("requires --force", result.stdout)

    # ── --force allows destructive operations ──────────────

    def test_restore_with_force_allowed(self) -> None:
        """Restore with --force → allowed (even if snapshot missing)."""
        result = _run_backup("--json", "restore", "2026-01-01-000000",
                             "--force", cwd=self.workspace)
        # Exit 2 because snapshot doesn't exist, not because force was rejected
        self.assertIn("snapshot not found", result.stdout)

    def test_restore_file_with_force_allowed(self) -> None:
        """Restore-file with --force → allowed."""
        result = _run_backup(
            "--json", "restore-file", "2026-01-01-000000", "test.py",
            "--force", cwd=self.workspace,
        )
        # Exit 2 because snapshot doesn't exist, not force rejection
        self.assertIn("snapshot not found", result.stdout)

    # ── Prune with force ───────────────────────────────────

    def test_prune_with_force_allowed(self) -> None:
        """Prune with --force → allowed."""
        result = _run_backup("--json", "prune", "--keep", "5", "--force",
                             cwd=self.workspace)
        self.assertEqual(result.returncode, 0,
                         f"Expected exit 0, got {result.returncode}")


if __name__ == "__main__":
    unittest.main()
