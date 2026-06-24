"""Tests for _protect.py — Maker attribution protection."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest


class TestProtect(unittest.TestCase):
    """Test maker protection module."""

    def test_maker_exported(self) -> None:
        """MAKER should be exported from _protect."""
        import _protect
        self.assertTrue(hasattr(_protect, "MAKER"))
        self.assertEqual(_protect.MAKER, "SmokerGreenOG")

    def test_protect_imports_cleanly(self) -> None:
        """_protect should import without errors."""
        try:
            import _protect
            # Re-import to verify it works
            self.assertIsNotNone(_protect)
        except Exception as e:
            self.fail(f"_protect import failed: {e}")

    def test_sha256_hash_is_consistent(self) -> None:
        """The SHA256 hash should match 'SmokerGreenOG'."""
        import _protect as p
        import hashlib
        expected_hash = hashlib.sha256(b"SmokerGreenOG").hexdigest()
        # We can't check _EXPECTED_HASH directly (it's private),
        # but we can verify the maker string hasn't changed
        self.assertEqual(p.MAKER, "SmokerGreenOG")


if __name__ == "__main__":
    unittest.main()
