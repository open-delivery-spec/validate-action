"""Run scripts/run-local.sh against a stub `ods` CLI.

Asserts the arguments the script hands the CLI, the report it renders and
the exit status a pre-push hook would see. Runs on the stock macOS bash 3.2
as well as on bash 5.
"""
import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run-local.sh"

_CLEAN = {
    "detect": {"stdout": {"ai_generated": False, "confidence": 0, "evidence": [],
                          "sources": [], "files": [], "summary": "No AI detected"}},
    "analyze": {"stdout": {"issues": [], "total_lines": 12, "summary": "No issues"}},
    "score": {"stdout": {"technical_debt_delta": 0.2, "verdict": "neutral", "risk": "low",
                         "breakdown": {}}},
    "check": {"stdout": {"allowed": True, "denials": [], "warnings": []}},
}


class LocalRun:
    def __init__(self, proc, out_dir):
        self.code = proc.returncode
        self.stdout = proc.stdout
        self.stderr = proc.stderr
        self.out_dir = out_dir

    def stage(self, name):
        return json.loads((self.out_dir / f"{name}.json").read_text())


@pytest.fixture
def run_local(bash, git_repo, fake_ods, clean_env):
    fake_ods.config = json.loads(json.dumps(_CLEAN))

    def run(*args, **env):
        proc = subprocess.run(
            [bash, str(SCRIPT), "--diff-base", "HEAD~1", *args],
            cwd=git_repo, env=clean_env(**fake_ods.env(), **env),
            capture_output=True, text=True, timeout=120,
        )
        return LocalRun(proc, git_repo / ".ods" / "out")

    return run


class TestResult:
    def test_clean_change_passes(self, run_local):
        run = run_local()
        assert run.code == 0, run.stderr
        assert "Result:  pass" in run.stdout
        for name in ("ods-summary.md", "index.html", "ods-report.json"):
            assert (run.out_dir / name).is_file()

    def test_policy_denial_fails_like_the_ci_gate(self, run_local, fake_ods):
        fake_ods.config["check"] = {"stdout": {"allowed": False, "denials": ["nope"],
                                               "warnings": []}, "exit": 1}
        run = run_local()
        assert run.code == 1
        assert "Result:  block" in run.stdout
        assert "ODS policy blocked this change." in run.stderr

    def test_detect_without_valid_output_is_inconclusive(self, run_local, fake_ods):
        fake_ods.config["detect"] = {"stdout": "", "exit": 1}
        run = run_local()
        assert run.stage("detect")["_ods_detect_error"] is True
        assert "Result:  warn" in run.stdout


class TestArguments:
    def test_flags_reach_the_cli(self, run_local, fake_ods, git_repo):
        (git_repo / "policy.rego").write_text("package ods.policy\n")
        body = "-f --json\n## AI Disclosure"
        run = run_local("--branch", "feature/x", "--commits", "3", "--policy", "policy.rego",
                        "--pr-body", body)
        assert run.code == 0, run.stderr
        assert fake_ods.argv("detect") == [
            "detect", "--json", "--diff-base", "HEAD~1", "--commits", "3",
            "--branch", "feature/x", "--pr-body", body,
        ]
        assert fake_ods.argv("check") == ["check", "--json", "--policy", "policy.rego"]
        assert fake_ods.calls("detect")[0]["env"]["ODS_BRANCH"] == "feature/x"

    def test_pr_file_and_missing_policy(self, run_local, fake_ods, git_repo):
        (git_repo / "body.md").write_text("## AI Disclosure\n")
        run_local("--pr-file", "body.md", "--policy", "missing.rego")
        argv = fake_ods.argv("detect")
        assert argv[argv.index("--pr-file") + 1] == "body.md"
        assert argv[argv.index("--branch") + 1] == "main"  # the checked-out branch
        assert fake_ods.argv("check") == ["check", "--json"]

    def test_output_dir(self, run_local, git_repo):
        run = run_local("--output-dir", "out")
        assert run.code == 0, run.stderr
        assert (git_repo / "out" / "ods-summary.md").is_file()

    def test_unknown_argument_is_a_usage_error(self, run_local):
        run = run_local("--bogus")
        assert run.code == 2
        assert "error: unknown argument: --bogus" in run.stderr
        assert "Usage:" in run.stdout

    def test_help(self, run_local):
        run = run_local("--help")
        assert run.code == 0
        assert "run-local.sh — run the ODS pipeline locally" in run.stdout
        assert "set -euo" not in run.stdout


def test_missing_cli_is_reported(bash, git_repo, tmp_path):
    empty = tmp_path / "empty-path"
    empty.mkdir()
    proc = subprocess.run([bash, str(SCRIPT)], cwd=git_repo, env={"PATH": str(empty)},
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 127
    assert "error: 'ods' not found on PATH." in proc.stderr
