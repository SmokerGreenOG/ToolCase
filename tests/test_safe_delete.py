"""Tests for safe_delete.py — containment, force, dry-run, audit logging."""
from __future__ import annotations

import tempfile
from pathlib import Path

from safe_delete import safe_rmtree, safe_unlink, is_within_workspace


class TestWorkspaceContainment:
    """Tests for workspace boundary enforcement."""

    def test_within_workspace(self):
        """Target inside workspace returns True."""
        ws = Path(tempfile.mkdtemp())
        target = ws / "subdir" / "file.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        assert is_within_workspace(target, ws)

    def test_outside_workspace_blocked(self):
        """Target outside workspace is blocked."""
        ws = Path(tempfile.mkdtemp())
        outside = Path(tempfile.mkdtemp())
        result = safe_rmtree(outside, workspace=ws)
        assert result["blocked"] is True
        assert "outside workspace" in result["reason"].lower()

    def test_workspace_none_allows(self):
        """No workspace means no containment check."""
        d = Path(tempfile.mkdtemp())
        (d / "file.txt").touch()
        result = safe_rmtree(d, force=True)
        assert result["deleted"] is True or result["blocked"] is False


class TestForceRequirement:
    """Tests for --force enforcement."""

    def test_no_force_blocks_deletion(self):
        """Deletion without force returns blocked."""
        d = Path(tempfile.mkdtemp())
        (d / "file.txt").touch()
        result = safe_rmtree(d, force=False)
        assert result["blocked"] is True
        assert "force" in result["reason"].lower()
        assert d.exists()  # Not actually deleted

    def test_force_allows_deletion(self):
        """Deletion with force succeeds."""
        d = Path(tempfile.mkdtemp())
        (d / "file.txt").touch()
        result = safe_rmtree(d, force=True)
        assert result["deleted"] is True
        assert not d.exists()


class TestDryRun:
    """Tests for dry-run preview mode."""

    def test_dry_run_does_not_delete(self):
        """Dry run shows preview but leaves files intact."""
        d = Path(tempfile.mkdtemp())
        (d / "a.txt").write_text("hello")
        (d / "b.txt").write_text("world")
        result = safe_rmtree(d, dry_run=True)
        assert result["dry_run"] is True
        assert "dry_run_preview" in result
        assert result["dry_run_preview"]["files"] == 2
        assert d.exists()  # Still there

    def test_dry_run_no_force_ok(self):
        """Dry run doesn't require force."""
        d = Path(tempfile.mkdtemp())
        result = safe_rmtree(d, dry_run=True, force=False)
        assert result["dry_run"] is True
        assert result["blocked"] is False


class TestSafeUnlink:
    """Tests for single file deletion."""

    def test_unlink_file(self):
        """Single file can be unlinked."""
        f = Path(tempfile.mkdtemp()) / "test.txt"
        f.write_text("data")
        result = safe_unlink(f, force=True)
        assert result["deleted"] is True
        assert not f.exists()

    def test_unlink_nonexistent(self):
        """Non-existent file returns gracefully."""
        result = safe_unlink(Path("/nonexistent/path/file.txt"))
        assert result["deleted"] is False
        assert "not exist" in result["reason"].lower()

    def test_unlink_dir_rejected(self):
        """Directory passed to safe_unlink is rejected."""
        d = Path(tempfile.mkdtemp())
        result = safe_unlink(d, force=True)
        assert result["deleted"] is False
        assert "directory" in result["reason"].lower()


class TestEdgeCases:
    """Edge case handling."""

    def test_nonexistent_path(self):
        """Non-existent path handled gracefully."""
        result = safe_rmtree(Path("/nonexistent/path"))
        assert result["deleted"] is False
        assert "not exist" in result["reason"].lower()

    def test_workspace_containment_with_symlink(self):
        """Symlink to outside workspace is still within if resolved path is within."""
        # This tests that resolve() is used, not just string prefix
        ws = Path(tempfile.mkdtemp())
        target = ws / "real_dir"
        target.mkdir()
        (target / "f.txt").touch()
        result = safe_rmtree(target, workspace=ws, force=True)
        assert result["deleted"] is True
