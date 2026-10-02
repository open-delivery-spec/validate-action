"""Run the shell steps of action.yml against a stub `ods` CLI.

Each test executes a step's real `run:` script with bash, in a scratch git
repository, with the step's `env:` block filled in from the input defaults in
action.yml. The stub records every `ods` call, so the tests can assert the
exact argument vectors the action builds, the files it leaves behind, and the
step outputs and exit status a workflow sees.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
ACTION = yaml.safe_load((REPO / "action.yml").read_text())
STEPS = {step["name"]: step for step in ACTION["runs"]["steps"] if "name" in step}
_INPUT_EXPR = re.compile(r"^\$\{\{\s*inputs\.([\w-]+)\s*\}\}$")


def step_env(name, **overrides):
    """The step's `env:` block: each `${{ inputs.x }}` at the input's default,
    any other expression empty, and ACTION_DIR at this checkout."""
    env = {}
    for key, expr in (STEPS[name].get("env") or {}).items():
        match = _INPUT_EXPR.match(str(expr))
        env[key] = str(ACTION["inputs"][match.group(1)].get("default", "")) if match else ""
    if "ACTION_DIR" in env:
        env["ACTION_DIR"] = str(REPO)
    env.update(overrides)
    return env


def run_step(bash, name, cwd, env):
    """Run a step the way the runner does: `bash --noprofile --norc -eo pipefail`."""
    return subprocess.run(
        [bash, "--noprofile", "--norc", "-eo", "pipefail", "-c", STEPS[name]["run"]],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
    )


def read_outputs(path):
    """key=value lines of a GITHUB_OUTPUT file; the last write wins."""
    if not path.exists():
        return {}
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


_HELP_CHECK = "Flags:\n      --ai-review stringArray\n      --mutation string\n      --policy string\n"
_HELP_CHECK_OLD = "Flags:\n      --policy string\n"

_CLEAN = {
    "detect": {"stdout": {"ai_generated": False, "confidence": 0, "evidence": [],
                          "sources": [], "files": [], "summary": "No AI detected"}},
    "analyze": {"stdout": {"issues": [], "total_lines": 12, "summary": "No issues"}},
    "score": {"stdout": {"technical_debt_delta": 0.2, "verdict": "neutral", "risk": "low",
                         "recommendation": "Acceptable for merge", "breakdown": {}}},
    "check": {"stdout": {"allowed": True, "denials": [], "warnings": [], "review_tier": "standard"},
              "help": _HELP_CHECK},
    "attest": {"help": "Write the AI-code evidence document"},
}

_VERDICT = {
    "schema": "ods.dev/review-verdict/v1",
    "reviewer": {"tool": "claude-code"},
    "verdict": "request_changes",
    "findings": [{"file": "a.go", "line": 3, "severity": "high", "message": "off by one"}],
}


class PipelineRun:
    def __init__(self, proc, outputs, report_dir, summary):
        self.code = proc.returncode
        self.stdout = proc.stdout
        self.stderr = proc.stderr
        self.outputs = outputs
        self.report_dir = report_dir
        self.summary = summary

    def stage(self, name):
        return json.loads((self.report_dir / f"{name}.json").read_text())


@pytest.fixture
def pipeline(runner_bash, git_repo, fake_ods, clean_env, tmp_path):
    """Runs the "Run ODS Pipeline" step; keyword arguments override its env."""
    fake_ods.config = json.loads(json.dumps(_CLEAN))

    def run(cwd=git_repo, **env_overrides):
        output_file = tmp_path / "github_output"
        summary_file = tmp_path / "step_summary"
        output_file.write_text("")
        summary_file.write_text("")
        env = clean_env(
            **step_env("Run ODS Pipeline", ODS_DIFF_BASE="HEAD~1", **env_overrides),
            **fake_ods.env(),
            GITHUB_OUTPUT=output_file,
            GITHUB_STEP_SUMMARY=summary_file,
        )
        proc = run_step(runner_bash, "Run ODS Pipeline", cwd, env)
        report_dir = Path(cwd) / env["ODS_OUTPUT_DIR"]
        return PipelineRun(proc, read_outputs(output_file), report_dir, summary_file.read_text())

    return run


# ── Run ODS Pipeline ──────────────────────────────────────────────────────────

class TestPipelineResult:
    def test_clean_run_passes_with_every_output_and_report_file(self, pipeline):
        run = pipeline()
        assert run.code == 0, run.stderr
        assert run.outputs == {
            "result": "pass", "ai_detected": "false", "ai_confidence": "0",
            "tech_debt_delta": "0.2", "policy_allowed": "true",
            "review_tier": "standard", "pipeline_integrity": "ok",
        }
        for name in ("ods-summary.md", "ods-report.json", "index.html", "ods-badge.svg",
                     "evidence.cdx.json"):
            assert (run.report_dir / name).is_file(), name
        assert (run.report_dir / ".result").read_text() == "pass"
        assert "<!-- ods-compliance-report -->" in run.summary

    def test_policy_denial_blocks_and_fails_the_step(self, pipeline, fake_ods):
        fake_ods.config["check"].update(
            stdout={"allowed": False, "denials": ["CRITICAL: injection"], "warnings": []}, exit=1)
        run = pipeline()
        assert run.code == 1
        assert "::error::ODS policy blocked this change" in run.stdout
        assert run.outputs["result"] == "block"
        assert run.outputs["policy_allowed"] == "false"
        # The report and the evidence document exist for the blocked change.
        assert "CRITICAL: injection" in (run.report_dir / "ods-summary.md").read_text()
        assert (run.report_dir / "evidence.cdx.json").is_file()

    def test_findings_reported_with_a_nonzero_exit_are_kept(self, pipeline, fake_ods):
        # analyze and score exit non-zero when they find something; that output
        # is the result, not a failure.
        issue = {"rule": "ai-hardcoded-secret", "file": "a.go", "line": 3,
                 "severity": "high", "message": "secret"}
        fake_ods.config["analyze"].update(
            stdout={"issues": [issue], "total_lines": 3, "summary": "1 issue"}, exit=1)
        fake_ods.config["score"].update(exit=1)
        run = pipeline()
        assert run.code == 0, run.stderr
        assert run.stage("analyze")["issues"] == [issue]
        assert "_ods_stage_error" not in run.stage("score")
        assert run.outputs["pipeline_integrity"] == "ok"
        assert "::warning::" not in run.stdout

    @pytest.mark.parametrize("stage,warning", [
        ("analyze", "::warning::ods analyze produced no valid output (exit=2)"),
        ("score", "::warning::ods score produced no valid output (exit=2)"),
        ("check", "::warning::ods check produced no valid verdict (exit=2)"),
    ])
    def test_stage_without_valid_json_is_inconclusive(self, pipeline, fake_ods, stage, warning):
        fake_ods.config[stage].update(stdout="panic: boom", stderr="goroutine 1 trace", exit=2)
        run = pipeline()
        assert run.code == 0, run.stderr
        assert warning in run.stdout
        assert f"--- ods {stage} error output ---" in run.stdout
        assert "goroutine 1 trace" in run.stdout
        assert run.stage(stage)["_ods_stage_error"] is True
        assert run.outputs["result"] == "warn"
        assert run.outputs["pipeline_integrity"] == "inconclusive"

    def test_crashed_gate_is_never_an_allowed_pass(self, pipeline, fake_ods):
        fake_ods.config["check"].update(stdout="", exit=2)
        run = pipeline()
        assert run.outputs["result"] == "warn"
        assert run.stage("check")["summary"] == "Policy check inconclusive (ods check exited 2)"

    def test_failure_mode_block_fails_on_an_inconclusive_stage(self, pipeline, fake_ods):
        fake_ods.config["score"].update(stdout="", exit=2)
        run = pipeline(ODS_FAILURE_MODE="block")
        assert run.code == 1
        assert run.outputs["result"] == "block"
        assert "::error::ODS policy blocked this change" in run.stdout

    def test_detect_without_valid_output_is_inconclusive(self, pipeline, fake_ods):
        fake_ods.config["detect"] = {"stdout": "", "stderr": "fatal: bad revision", "exit": 1}
        run = pipeline()
        assert run.code == 0, run.stderr
        assert "::warning::ods detect produced no valid output (exit=1)" in run.stdout
        assert "fatal: bad revision" in run.stdout
        assert run.stage("detect")["_ods_detect_error"] is True
        assert run.outputs["result"] == "warn"

    def test_reports_left_by_an_earlier_run_are_removed(self, pipeline, fake_ods, git_repo):
        stale = git_repo / "ods-report"
        stale.mkdir()
        (stale / "ai-review-3.json").write_text(json.dumps(_VERDICT))
        (stale / "evidence.cdx.json").write_text("stale")
        (stale / "ods-summary.md").write_text("stale")
        (stale / ".result").write_text("block")
        del fake_ods.config["attest"]  # this CLI writes no evidence document
        run = pipeline()
        assert run.code == 0, run.stderr
        assert not (stale / "ai-review-3.json").exists()
        assert not (stale / "evidence.cdx.json").exists()
        assert "AI Review" not in (stale / "ods-summary.md").read_text()
        assert (stale / ".result").read_text() == "pass"


class TestDetectArguments:
    def test_pr_body_reaches_detect_as_one_argument(self, pipeline, fake_ods):
        body = ("Repair with `git push -f origin v1` or --force.\n"
                "-f --json --policy /dev/null\n"
                "## AI Disclosure\n- [x] This PR contains AI-generated code\n")
        run = pipeline(ODS_PR_BODY=body)
        assert run.code == 0, run.stderr
        assert fake_ods.argv("detect") == [
            "detect", "--json", "--diff-base", "HEAD~1", "--commits", "10",
            "--pr-body", body, "--branch", "main",
        ]

    def test_pr_body_file(self, pipeline, fake_ods, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("## AI Disclosure\n")
        pipeline(ODS_PR_BODY_FILE=body_file)
        argv = fake_ods.argv("detect")
        assert argv[argv.index("--pr-file") + 1] == str(body_file)
        assert "--pr-body" not in argv

    def test_pr_body_from_the_event_payload(self, pipeline, fake_ods, tmp_path):
        event = tmp_path / "event.json"
        event.write_text(json.dumps({"pull_request": {"body": "-x from the event"}}))
        pipeline(GITHUB_EVENT_PATH=event)
        argv = fake_ods.argv("detect")
        assert argv[argv.index("--pr-body") + 1] == "-x from the event"

    def test_event_without_a_body_adds_no_pr_body(self, pipeline, fake_ods, tmp_path):
        event = tmp_path / "event.json"
        event.write_text(json.dumps({"pull_request": {"body": None}}))
        pipeline(GITHUB_EVENT_PATH=event)
        assert "--pr-body" not in fake_ods.argv("detect")

    @pytest.mark.parametrize("branch_input,head_ref,expected", [
        ("feature/input", "feature/head-ref", "feature/input"),
        ("", "feature/head-ref", "feature/head-ref"),
        ("", "", "main"),  # the checked-out branch
    ])
    def test_branch_resolution(self, pipeline, fake_ods, branch_input, head_ref, expected):
        pipeline(ODS_BRANCH=branch_input, GITHUB_HEAD_REF=head_ref)
        argv = fake_ods.argv("detect")
        assert argv[argv.index("--branch") + 1] == expected
        # Exported too: the CLI reads ODS_BRANCH when the checkout has no branch.
        assert fake_ods.calls("detect")[0]["env"]["ODS_BRANCH"] == expected

    def test_shallow_checkout_is_flagged(self, pipeline, fake_ods, git_repo, tmp_path, clean_env):
        shallow = tmp_path / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "1", git_repo.as_uri(), str(shallow)],
                       env=clean_env(), check=True, capture_output=True)
        run = pipeline(cwd=shallow)
        assert run.code == 0, run.stderr
        assert "::warning::Shallow checkout detected" in run.stdout
        assert "::warning::diff-base 'HEAD~1' does not resolve in this checkout" in run.stdout
        assert fake_ods.calls("detect")[0]["env"]["ODS_SHALLOW_CHECKOUT"] == "true"
        report = json.loads((run.report_dir / "ods-report.json").read_text())
        assert report["pipeline"]["shallow_checkout"] is True


class TestGateInputs:
    def test_policy_passed_only_when_the_file_exists(self, pipeline, fake_ods, git_repo):
        pipeline()
        assert "--policy" not in fake_ods.argv("check")
        assert "--policy" not in fake_ods.argv("attest")

        (git_repo / ".ods").mkdir()
        (git_repo / ".ods" / "policy.rego").write_text("package ods.policy\n")
        fake_ods.log_path.unlink()
        pipeline()
        for stage in ("check", "attest"):
            argv = fake_ods.argv(stage)
            assert argv[argv.index("--policy") + 1] == ".ods/policy.rego"

    def test_user_sarif_reaches_analyze_score_check_and_attest(self, pipeline, fake_ods, tmp_path):
        sarif = tmp_path / "user.sarif"
        sarif.write_text("{}")
        generated = tmp_path / "semgrep.sarif"
        generated.write_text("{}")
        run = pipeline(ODS_SARIF=sarif, ODS_GENERATED_SARIF=generated)
        assert f"Merging external SARIF findings from: {sarif}" in run.stdout
        for stage in ("analyze", "score", "check", "attest"):
            argv = fake_ods.argv(stage)
            assert argv[argv.index("--sarif") + 1] == str(sarif), stage
            assert str(generated) not in argv

    def test_generated_sarif_is_used_without_a_user_sarif(self, pipeline, fake_ods, tmp_path):
        generated = tmp_path / "semgrep.sarif"
        generated.write_text("{}")
        pipeline(ODS_GENERATED_SARIF=generated)
        argv = fake_ods.argv("analyze")
        assert argv[argv.index("--sarif") + 1] == str(generated)

    def test_missing_sarif_is_skipped_with_a_warning(self, pipeline, fake_ods):
        run = pipeline(ODS_SARIF="nope.sarif")
        assert "::warning::SARIF file 'nope.sarif' not found — skipping SARIF merge" in run.stdout
        assert "--sarif" not in fake_ods.argv("analyze")

    def test_ai_review_paths_are_split_trimmed_and_copied(self, pipeline, fake_ods, git_repo):
        (git_repo / "a.json").write_text(json.dumps(_VERDICT))
        (git_repo / "b.json").write_text(json.dumps({**_VERDICT, "verdict": "approve"}))
        run = pipeline(ODS_AI_REVIEW=" a.json , b.json\nmissing.json\n")
        assert run.code == 0, run.stderr
        argv = fake_ods.argv("check")
        assert argv[argv.index("--ai-review"):] == ["--ai-review", "a.json", "--ai-review", "b.json"]
        assert "::warning::ai-review file 'missing.json' not found — skipping" in run.stdout
        assert json.loads((run.report_dir / "ai-review-0.json").read_text()) == _VERDICT
        assert json.loads((run.report_dir / "ai-review-1.json").read_text())["verdict"] == "approve"
        assert "### 🧠 AI Review" in (run.report_dir / "ods-summary.md").read_text()

    def test_ai_review_is_ignored_by_a_cli_without_the_flag(self, pipeline, fake_ods, git_repo):
        (git_repo / "a.json").write_text(json.dumps(_VERDICT))
        fake_ods.config["check"]["help"] = _HELP_CHECK_OLD
        run = pipeline(ODS_AI_REVIEW="a.json")
        assert run.code == 0, run.stderr
        assert "predates 'ods check --ai-review' — ignoring the ai-review input" in run.stdout
        assert "--ai-review" not in fake_ods.argv("check")
        assert not list(run.report_dir.glob("ai-review-*.json"))

    def test_mutation_report_is_passed_when_supported(self, pipeline, fake_ods, git_repo):
        (git_repo / "gremlins.json").write_text("{}")
        run = pipeline(ODS_MUTATION="gremlins.json")
        assert "Feeding mutation report from: gremlins.json" in run.stdout
        argv = fake_ods.argv("check")
        assert argv[argv.index("--mutation") + 1] == "gremlins.json"

    def test_mutation_report_missing_or_unsupported_is_skipped(self, pipeline, fake_ods, git_repo):
        run = pipeline(ODS_MUTATION="gone.json")
        assert "::warning::mutation-report file 'gone.json' not found — skipping" in run.stdout
        assert "--mutation" not in fake_ods.argv("check")

        (git_repo / "gremlins.json").write_text("{}")
        fake_ods.config["check"]["help"] = _HELP_CHECK_OLD
        fake_ods.log_path.unlink()
        run = pipeline(ODS_MUTATION="gremlins.json")
        assert "predates 'ods check --mutation' — ignoring the mutation-report input" in run.stdout
        assert "--mutation" not in fake_ods.argv("check")


class TestEvidenceDocument:
    def test_attest_records_what_the_gate_evaluated(self, pipeline, fake_ods):
        run = pipeline()
        assert fake_ods.argv("attest")[:3] == ["attest", "--out", "ods-report/evidence.cdx.json"]
        # The pipeline integrity computed by the report reaches the document.
        assert fake_ods.calls("attest")[0]["env"]["ODS_PIPELINE_INTEGRITY"] == "ok"
        assert "Evidence document written to ods-report/evidence.cdx.json" in run.stdout

    def test_attest_failure_is_a_warning(self, pipeline, fake_ods):
        fake_ods.config["attest"].update(stderr="cannot write", exit=1)
        run = pipeline()
        assert run.code == 0, run.stderr
        assert "::warning::ods attest failed — evidence document skipped" in run.stdout
        assert "cannot write" in run.stdout

    def test_older_cli_skips_the_evidence_document(self, pipeline, fake_ods):
        del fake_ods.config["attest"]
        run = pipeline()
        assert run.code == 0, run.stderr
        assert "Installed ODS CLI predates 'ods attest'" in run.stdout
        assert fake_ods.calls("attest") == []


# ── Run Semgrep (optional) ────────────────────────────────────────────────────

def test_semgrep_step_defers_to_a_user_sarif(bash, git_repo, stub, clean_env, tmp_path):
    # A python3 that fails proves Semgrep is never installed in this case.
    stub("python3", "import sys; sys.exit(1)")
    output_file = tmp_path / "github_output"
    output_file.write_text("")
    env = clean_env(**step_env("Run Semgrep (optional)", USER_SARIF="mine.sarif"),
                    GITHUB_OUTPUT=output_file)
    proc = run_step(bash, "Run Semgrep (optional)", git_repo, env)
    assert proc.returncode == 0, proc.stderr
    assert "using the provided sarif and skipping Semgrep" in proc.stdout
    assert output_file.read_text() == ""


# ── AI Attribution Report (optional) ──────────────────────────────────────────

_ATTRIBUTION = {"since": "90 days ago", "total_commits": 4, "ai_commits": 1,
                "human_commits": 3, "ai_commit_share": 0.25, "total_changed_lines": 100,
                "ai_changed_lines": 10, "ai_line_share": 0.1, "by_tool": {"Claude": 1}}


@pytest.fixture
def attribution(bash, git_repo, fake_ods, clean_env, tmp_path):
    def run():
        summary_file = tmp_path / "step_summary"
        summary_file.write_text("")
        env = clean_env(**step_env("AI Attribution Report (optional)"), **fake_ods.env(),
                        GITHUB_STEP_SUMMARY=summary_file)
        proc = run_step(bash, "AI Attribution Report (optional)", git_repo, env)
        return proc, summary_file.read_text()
    return run


class TestAttributionStep:
    def test_digest_reaches_the_report_comment_and_job_summary(self, attribution, fake_ods, git_repo):
        fake_ods.config["report"] = {"stdout": _ATTRIBUTION, "help": "      --html string\n"}
        (git_repo / "ods-report").mkdir()
        (git_repo / "ods-report" / "ods-summary.md").write_text("## ODS AI Code Report\n")
        proc, job_summary = attribution()
        assert proc.returncode == 0, proc.stderr
        digest = (git_repo / "ods-report" / "ods-attribution.md").read_text()
        assert "## 📊 AI Attribution — 90 days ago" in digest
        assert "`ai-attribution.html`" in digest
        assert digest.strip() in (git_repo / "ods-report" / "ods-summary.md").read_text()
        assert digest.strip() in job_summary
        report_calls = [c["argv"] for c in fake_ods.calls("report")]
        assert ["report", "--since", "90 days ago", "--json"] in report_calls
        assert ["report", "--since", "90 days ago", "--html",
                "ods-report/ai-attribution.html"] in report_calls

    def test_report_failure_is_a_warning(self, attribution, fake_ods, git_repo):
        fake_ods.config["report"] = {"stderr": "not a git repository", "exit": 1}
        proc, job_summary = attribution()
        assert proc.returncode == 0, proc.stderr
        assert "::warning::ods report failed — skipping attribution digest" in proc.stdout
        assert job_summary == ""
        assert not (git_repo / "ods-report" / "ods-attribution.md").exists()


# ── Review routing ────────────────────────────────────────────────────────────

_FAKE_GH = '''\
import json, os, sys
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
sys.exit(1 if "--add-label" in sys.argv and os.environ.get("FAKE_GH_FAIL_LABEL") else 0)
'''


@pytest.fixture
def routing(runner_bash, git_repo, stub, clean_env, tmp_path):
    stub("gh", _FAKE_GH)
    log = tmp_path / "gh-log.jsonl"

    def run(**overrides):
        defaults = {"GH_TOKEN": "test-token", "PR_URL": "https://github.com/o/r/pull/7"}
        env = clean_env(**step_env("Review routing", **{**defaults, **overrides}),
                        FAKE_GH_LOG=log)
        proc = run_step(runner_bash, "Review routing", git_repo, env)
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return proc, calls

    return run


class TestReviewRouting:
    def test_elevated_tier_labels_the_pr_and_requests_reviewers(self, routing):
        proc, calls = routing(TIER="elevated", ELEVATED_REVIEWERS=" alice, bob ,,")
        assert proc.returncode == 0, proc.stderr
        pr = "https://github.com/o/r/pull/7"
        assert [c[:3] for c in calls if c[0] == "label"] == [
            ["label", "create", "ods:review/auto"],
            ["label", "create", "ods:review/standard"],
            ["label", "create", "ods:review/elevated"],
        ]
        assert [c for c in calls if c[0] == "pr"] == [
            ["pr", "edit", pr, "--remove-label", "ods:review/auto"],
            ["pr", "edit", pr, "--remove-label", "ods:review/standard"],
            ["pr", "edit", pr, "--add-label", "ods:review/elevated"],
            ["pr", "edit", pr, "--add-reviewer", "alice"],
            ["pr", "edit", pr, "--add-reviewer", "bob"],
        ]

    def test_missing_tier_routes_standard_without_reviewers(self, routing):
        proc, calls = routing(TIER="", ELEVATED_REVIEWERS="alice")
        assert "Review tier: standard" in proc.stdout
        assert ["pr", "edit", "https://github.com/o/r/pull/7", "--add-label",
                "ods:review/standard"] in calls
        assert not [c for c in calls if "--add-reviewer" in c]

    def test_label_failure_is_a_warning(self, routing):
        proc, _ = routing(TIER="auto", FAKE_GH_FAIL_LABEL="1")
        assert proc.returncode == 0, proc.stderr
        assert "::warning::Could not apply review-tier label" in proc.stdout

    def test_empty_token_skips_routing(self, routing):
        proc, calls = routing(TIER="elevated", GH_TOKEN="")
        assert proc.returncode == 0
        assert "::warning::Skipping review routing because github-token is empty." in proc.stdout
        assert calls == []
