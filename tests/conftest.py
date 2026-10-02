"""Fixtures for the tests that execute the action's shell steps.

The steps in action.yml and scripts/run-local.sh run for real, with bash, git
and python3, against a stub `ods` CLI that answers from a per-test config and
records every call. Nothing touches the network or the surrounding job: each
step gets an environment built from scratch, so a CI run's GITHUB_* variables
never leak into the step under test.
"""
import json
import os
import shutil
import stat
import subprocess
import sys

import pytest

# Stub `ods`: answers from FAKE_ODS_CONFIG ({subcommand: spec}) and appends
# {"argv": [...], "env": {...}} to FAKE_ODS_LOG for every call. A spec holds
# `stdout` (a string, or an object written as JSON), `stderr`, `exit`, and
# `help` (printed for `<subcommand> --help`; without it --help fails, like an
# unknown command on an older CLI). `--out <file>` writes "{}" to the file.
_FAKE_ODS = '''\
import json, os, sys

args = sys.argv[1:]
seen = ("ODS_BRANCH", "ODS_SHALLOW_CHECKOUT", "ODS_PIPELINE_INTEGRITY")
with open(os.environ["FAKE_ODS_LOG"], "a") as log:
    log.write(json.dumps({"argv": args, "env": {k: os.environ.get(k) for k in seen}}) + "\\n")
with open(os.environ["FAKE_ODS_CONFIG"]) as f:
    spec = json.load(f).get(args[0] if args else "", {})
if "--help" in args:
    sys.stdout.write(spec.get("help", ""))
    sys.exit(0 if "help" in spec else 1)
if "--out" in args:
    with open(args[args.index("--out") + 1], "w") as f:
        f.write("{}")
out = spec.get("stdout", "")
sys.stdout.write(out if isinstance(out, str) else json.dumps(out))
sys.stderr.write(spec.get("stderr", ""))
sys.exit(spec.get("exit", 0))
'''


def write_stub(path, python_source):
    """Write an executable Python stub run by the interpreter running the tests."""
    path.write_text(f"#!{sys.executable}\n{python_source}")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture(scope="session")
def bash():
    path = shutil.which("bash")
    if not path or not shutil.which("git"):
        pytest.skip("needs bash and git")
    return path


@pytest.fixture(scope="session")
def runner_bash(bash):
    """bash as on GitHub runners. The composite steps expand empty arrays under
    `set -u`, which bash allows only from 4.4 on (macOS still ships 3.2)."""
    version = subprocess.run(
        [bash, "-c", 'echo "${BASH_VERSINFO[0]} ${BASH_VERSINFO[1]}"'],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    if (int(version[0]), int(version[1])) < (4, 4):
        pytest.skip("the action's steps need bash >= 4.4, as on GitHub runners")
    return bash


@pytest.fixture
def stub_bin(tmp_path):
    """A directory put first on PATH for the step under test."""
    path = tmp_path / "bin"
    path.mkdir()
    return path


@pytest.fixture
def stub(stub_bin):
    """Factory: install an executable Python stub called `name` on that PATH."""
    def make(name, python_source):
        write_stub(stub_bin / name, python_source)
    return make


@pytest.fixture
def clean_env(tmp_path, stub_bin):
    """Factory for a step environment: PATH with the stubs first, a throwaway
    HOME (no user git config), a fixed git identity, plus the given variables."""
    home = tmp_path / "home"
    home.mkdir()

    def make(**extra):
        env = {
            "PATH": f"{stub_bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(home),
            "TMPDIR": str(tmp_path),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
        }
        for key in ("LANG", "LC_ALL"):
            if key in os.environ:
                env[key] = os.environ[key]
        env.update({key: str(value) for key, value in extra.items()})
        return env

    return make


class FakeOds:
    def __init__(self, bin_dir, workdir):
        self.config_path = workdir / "fake-ods-config.json"
        self.log_path = workdir / "fake-ods-log.jsonl"
        self.config = {}
        write_stub(bin_dir / "ods", _FAKE_ODS)

    def env(self):
        """Variables the stub needs; call after setting `config`."""
        self.config_path.write_text(json.dumps(self.config))
        return {"FAKE_ODS_CONFIG": self.config_path, "FAKE_ODS_LOG": self.log_path}

    def calls(self, subcommand):
        """Every recorded call of `subcommand`, --help probes excluded."""
        if not self.log_path.exists():
            return []
        calls = [json.loads(line) for line in self.log_path.read_text().splitlines()]
        return [c for c in calls if c["argv"][:1] == [subcommand] and "--help" not in c["argv"]]

    def argv(self, subcommand):
        """argv of the one call of `subcommand`."""
        calls = self.calls(subcommand)
        assert len(calls) == 1, calls
        return calls[0]["argv"]


@pytest.fixture
def fake_ods(stub_bin, tmp_path):
    return FakeOds(stub_bin, tmp_path)


@pytest.fixture
def git_repo(tmp_path, bash, clean_env):
    """A two-commit repository on branch main."""
    repo = tmp_path / "repo"
    repo.mkdir()
    env = clean_env()

    def git(*args):
        subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    for name in ("one.txt", "two.txt"):
        (repo / name).write_text(f"{name}\n")
        git("add", name)
        git("commit", "-q", "-m", f"add {name}")
    return repo
