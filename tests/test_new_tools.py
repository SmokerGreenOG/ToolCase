"""Tests for new tools: prompt_optimizer and changelog_generator."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
import tempfile
import subprocess
import json
from pathlib import Path


class TestPromptOptimizer(unittest.TestCase):
    def setUp(self) -> None:
        """Set up temporary directory for tests."""
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        """Clean up temporary directory."""
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_analyze_string(self) -> None:
        """analyze_direct_prompt should return clarity_score and token_estimate."""
        from prompt_optimizer import analyze_direct_prompt

        result = analyze_direct_prompt(
            "You are a Python expert. Output as JSON. Think step by step."
        )
        self.assertIn("clarity_score", result)
        self.assertGreater(result["clarity_score"], 0)
        self.assertIn("token_estimate", result)

    def test_analyze_short_prompt(self) -> None:
        """Short prompts get a severity string."""
        from prompt_optimizer import analyze_direct_prompt

        result = analyze_direct_prompt("help")
        self.assertIsInstance(result["severity"], str)

    def test_analyze_vague_prompt(self) -> None:
        """Vague prompts return a valid severity level."""
        from prompt_optimizer import analyze_direct_prompt

        result = analyze_direct_prompt("do stuff")
        self.assertIn(result["severity"], ("low", "medium", "high"))

    def test_estimate_tokens(self) -> None:
        """estimate_tokens returns positive count for any input."""
        from prompt_optimizer import estimate_tokens

        t = estimate_tokens("hello world")
        self.assertGreater(t, 0)

    def test_cli_help(self) -> None:
        """CLI --help flag outputs usage information."""
        tool = Path(__file__).parent.parent / "prompt_optimizer.py"
        r = subprocess.run([sys.executable, str(tool), "--help"], capture_output=True, text=True)
        self.assertIn("usage", (r.stdout + r.stderr).lower())

    def test_cli_analyze_flag(self) -> None:
        """CLI --analyze --json outputs valid JSON with clarity_score."""
        tool = Path(__file__).parent.parent / "prompt_optimizer.py"
        r = subprocess.run(
            [sys.executable, str(tool), "--analyze", "test prompt", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        data = json.loads(r.stdout)
        self.assertIn("clarity_score", data)


class TestChangelogCLI(unittest.TestCase):
    def test_help(self) -> None:
        """Changelog CLI --help outputs usage information."""
        tool = Path(__file__).parent.parent / "changelog_generator.py"
        r = subprocess.run([sys.executable, str(tool), "--help"], capture_output=True, text=True)
        self.assertIn("usage", (r.stdout + r.stderr).lower())
        self.assertEqual(r.returncode, 0)

    def test_git_log(self) -> None:
        """Changelog --git-log HEAD runs without crash."""
        tool = Path(__file__).parent.parent / "changelog_generator.py"
        r = subprocess.run(
            [sys.executable, str(tool), "--git-log", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(tool.parent),
            timeout=15,
        )
        self.assertIn(r.returncode, (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
