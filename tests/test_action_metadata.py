"""Tests for the step conditions declared in action.yml.

The pipeline step exits 1 on BLOCK. Every step that must still run after a
block — the report artifact upload and the PR comment — has to say so with
`always()`, or the composite skips it and a blocked PR ends up with no report,
no evidence document, and no comment explaining the block.
"""
from pathlib import Path

import yaml

ACTION = yaml.safe_load((Path(__file__).parent.parent / "action.yml").read_text())
STEPS = {step["name"]: step for step in ACTION["runs"]["steps"] if "name" in step}


def _condition(name):
    return STEPS[name].get("if", "")


class TestStepsAfterBlock:
    def test_upload_runs_when_the_gate_blocks(self):
        assert "always()" in _condition("Upload ODS Report")

    def test_comment_runs_when_the_gate_blocks(self):
        assert "always()" in _condition("Comment on Pull Request")

    def test_attribution_digest_runs_when_the_gate_blocks(self):
        assert "always()" in _condition("AI Attribution Report (optional)")

    def test_review_routing_is_skipped_when_the_gate_blocks(self):
        # Deny wins: a blocked PR is never routed, so this step must keep the
        # default success() condition and stay skipped after a failure.
        assert "always()" not in _condition("Review routing")

    def test_inputs_still_gate_the_steps(self):
        assert "inputs.artifact == 'true'" in _condition("Upload ODS Report")
        assert "inputs.comment == 'true'" in _condition("Comment on Pull Request")
        assert "github.event_name == 'pull_request'" in _condition("Comment on Pull Request")


class TestPipelineStartsClean:
    """The comment step now runs after a failed pipeline, so a summary left by
    an earlier invocation in the same job must be removed before this one
    starts — otherwise a crashed run could post a previous run's report."""

    def test_stale_report_files_are_removed_before_the_pipeline_runs(self):
        script = STEPS["Run ODS Pipeline"]["run"]
        cleanup = script.index("ods-summary.md")
        first_stage = script.index("ods detect --json")
        assert cleanup < first_stage
        for name in ("ods-summary.md", "ods-report.json", "evidence.cdx.json", ".result"):
            assert name in script[:first_stage]
