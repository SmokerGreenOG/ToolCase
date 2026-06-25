"""Tests for i18n.py — Translation module."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from i18n import t, get_lang, TRANS


class TestI18n(unittest.TestCase):
    """Test internationalization module."""

    def test_translation_exists_en(self) -> None:
        """All defined keys should have English translations."""
        for key, translations in TRANS.items():
            with self.subTest(key=key):
                if isinstance(translations, dict):
                    self.assertIn("en", translations, f"Key '{key}' missing English translation")
                # skip non-standard entries (e.g. lists)

    def test_translation_exists_nl(self) -> None:
        """All defined keys should have Dutch translations."""
        for key, translations in TRANS.items():
            with self.subTest(key=key):
                if isinstance(translations, dict):
                    self.assertIn("nl", translations, f"Key '{key}' missing Dutch translation")

    def test_translation_exists_de(self) -> None:
        """All defined keys should have German translations."""
        for key, translations in TRANS.items():
            with self.subTest(key=key):
                if isinstance(translations, dict):
                    self.assertIn("de", translations, f"Key '{key}' missing German translation")

    def test_t_function_returns_string(self) -> None:
        """t() should always return a string."""
        result = t("toolcase_title", lang="en", COUNT=53, VERSION="5.1.0")
        self.assertIsInstance(result, str)
        self.assertIn("53", result)
        self.assertIn("5.1.0", result)

    def test_t_missing_key_returns_questionmarks(self) -> None:
        """t() with unknown key should return ??key??."""
        result = t("nonexistent_key_xyz", lang="en")
        self.assertEqual(result, "??nonexistent_key_xyz??")

    def test_t_dutch_output(self) -> None:
        """Dutch output should contain Dutch words."""
        result = t("safety_rules_label", lang="nl")
        self.assertIn("Veiligheidsregels", result)

    def test_t_german_output(self) -> None:
        """German output should contain German words."""
        result = t("safety_rules_label", lang="de")
        self.assertIn("Sicherheitsregeln", result)

    def test_get_lang_default(self) -> None:
        """get_lang() should return a 2-char language code."""
        lang = get_lang()
        self.assertIn(lang, ("en", "nl", "de"))

    def test_format_with_variables(self) -> None:
        """t() should handle format variables."""
        result = t("file_not_found", lang="en", target="test.py")
        self.assertIn("test.py", result)

    def test_format_n_variable(self) -> None:
        """t() should handle {n} variable for counts."""
        result = t("issues_found", lang="en", n=42)
        self.assertIn("42", result)


if __name__ == "__main__":
    unittest.main()
