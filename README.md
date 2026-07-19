# ODS Validate Action

[![ODS Validate](https://github.com/open-delivery-spec/validate-action/actions/workflows/ods-validate.yml/badge.svg)](https://github.com/open-delivery-spec/validate-action/actions/workflows/ods-validate.yml)
[![CI](https://github.com/open-delivery-spec/validate-action/actions/workflows/self-test.yml/badge.svg)](https://github.com/open-delivery-spec/validate-action/actions/workflows/self-test.yml)

> **Zero-config AI code quality gate for teams using Claude Code, Copilot, or Cursor.** These tools already stamp `Co-Authored-By` trailers on every commit, so ODS attributes AI-generated code automatically in CI — then analyzes quality, scores technical debt, and enforces policy on every PR. No disclosure forms, no manual tagging.

---

## Why ODS?

AI writes code faster than ever, but AI code increases technical debt in predictable ways:

| AI Failure Mode | Real-world impact |
|---|---|
| **Hallucinated APIs** | AI invents functions, packages, endpoints that don’t exist |
| **Redundant error handling** | 3+ identical `if err != nil` blocks in the same function |
| **Over-commenting** | 35%+ comment-to-code ratio with self-explanatory comments |
| **Missing tests** | AI-generated PRs often ship with little or no accompanying tests |
| **Invisible AI code** | Teams can’t distinguish AI-generated from human-written changes |

This Action runs the full ODS pipeline on every PR so low-quality AI code never reaches production.

---

## Quick Start

```yaml
name: ODS AI Code Quality
on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write

jobs:
  ods:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0  # required for git diff against base
      - uses: open-delivery-spec/validate-action@v1
```

That’s it. The Action automatically:

1. **Attributes** AI-generated code (`Co-Authored-By` trailers, PR disclosure, branch names, diff heuristics)
2. **Analyzes** code quality (built-in rules for AI-specific defects, plus any external analyzer via SARIF)
3. **Scores** technical debt impact (5-dimension weighted model)
4. **Enforces** policy (OPA Rego — optional, place at `.ods/policy.rego`)

---

## Run It Locally

Iterate on detection and policy **without pushing a PR**. `scripts/run-local.sh`
runs the exact same detect → analyze → score → check pipeline this Action runs in
CI, then renders the same HTML/Markdown report locally.

```bash
# Requires the ods CLI on PATH:
#   go install github.com/open-delivery-spec/cli/cmd/ods@latest

scripts/run-local.sh                          # diff against origin/main
scripts/run-local.sh --diff-base HEAD~3       # last 3 commits
scripts/run-local.sh --policy .ods/policy.rego
```

Output lands in `.ods/out/` (`index.html`, `ods-summary.md`, and the raw
`detect/analyze/score/check.json`). The script exits non-zero when the policy
blocks the change — the same gate as CI — so you can wire it into a pre-push hook.

Flags: `--diff-base`, `--branch`, `--policy`, `--commits`, `--output-dir`,
`--pr-body`, `--pr-file` (run with `--help` for details).

---

## Versioning & Stability

Pin the Action to a major tag so you receive fixes without breaking changes:

```yaml
- uses: open-delivery-spec/validate-action@v1   # recommended: tracks the v1 line
# - uses: open-delivery-spec/validate-action@v1.0.0   # exact release, fully reproducible
```

> **Note on the CLI it installs.** By default the Action installs a **pinned
> stable release** of the ODS CLI (`cli-ref: v0.7.1`) so runs are reproducible.
> To always track the latest detection and analysis improvements, set it to
> `main` (or any tag/commit):
>
> ```yaml
> - uses: open-delivery-spec/validate-action@v1
>   with:
>     cli-ref: main   # latest; or a specific tag/commit like v0.7.1
> ```

---

## AI Attribution: `Co-Authored-By` as the Primary Signal

ODS reads `Co-Authored-By` trailers that AI tools already emit automatically:

| Tool | Emitted automatically | What ODS reads |
|------|-----------------------|----------------|
| **Claude / Claude Code** | Yes | `Co-Authored-By: Claude <noreply@anthropic.com>` |
| **GitHub Copilot** | Yes | `Co-Authored-By: GitHub Copilot <...@users.noreply.github.com>` |
| **Cursor** | Yes | `Co-Authored-By: Cursor <cursor@cursor.sh>` |

No configuration required — if your team uses any of these tools, AI attribution is detected automatically from the commits.

The [Linux kernel coding-assistants convention](https://docs.kernel.org/process/coding-assistants.html) is recognized as an equally strong disclosure — `Assisted-by: Claude:claude-3-opus coccinelle` attributes the commit to `Claude` with the model version surfaced in the evidence.

Repos using [git-ai](https://github.com/git-ai-project/git-ai) get the highest-fidelity signal: the Action fetches its `refs/notes/ai` authorship logs automatically (best effort) and the CLI *measures* per-file AI lines from them instead of estimating — with the agent and model named in the evidence. Repos without git-ai are unaffected.

ODS also reads supplemental ODS-specific trailer fields (`AI-assisted: true`, `AI-tool: name`) for teams that add them, but `Co-Authored-By` is sufficient on its own.

This is **attribution from signals the tools volunteer**, not forensic detection: an author who strips the trailer can evade it, and the diff heuristics are only a low-confidence fallback. ODS surfaces what AI tools disclose — it does not claim to unmask code that hides it.

---

## What You’ll See

### PR Comment (auto-posted)

> ## ODS AI Code Quality Report
>
> **Gate Result:** ✅ PASS  
> **AI Detected:** 👤 No (confidence: 0%)  
> **Tech Debt Delta:** +0.3 (neutral)  
> **Policy:** ✅ Allowed  
>
> ### 🔍 Detection
> No AI code detected.
>
> ### 📊 Analysis
> No quality issues detected
>
> ### 📈 Score
> | Dimension | Value |
> |-----------|-------|
> | AI Code Ratio | 0% |
> | Defect Density | 0.0 / KLOC |
> | Critical Issues | 0 |
> | Test Coverage | 0% |
> | Duplication Rate | 0% |
>
> **Verdict:** neutral — Moderate risk: review recommended, ensure adequate tests

### When AI code is detected:

> **Gate Result:** ✅ PASS  
> **AI Detected:** 🤖 Yes (confidence: 85%)  
> **Tech Debt Delta:** +4.2 (increase)  
> **Policy:** ✅ Allowed  
>
> ### 🔍 Detection
> | Source | Signal | Confidence |
> |--------|--------|------------|
> | Co-Authored-By | GitHub Copilot commit trailer | 80% |
> | pr-body | AI disclosure checkbox is checked | 85% |
>
> ### 📊 Analysis
> 3 issue(s) found: 1 high, 2 medium
> ...

### When policy blocks the PR:

> **Gate Result:** ❌ BLOCK  
> **Policy:** ❌ Blocked  
>
> ### 🚫 Policy Denials
> - ❌ AI code with low test coverage

---

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `diff-base` | No | `origin/main` | Git ref to diff against |
| `pr-body` | No | auto-detected | PR description body text |
| `pr-body-file` | No | — | Path to file containing PR body |
| `branch` | No | auto-detected | Branch name |
| `commits` | No | `10` | Max commits to scan for AI markers |
| `policy` | No | `.ods/policy.rego` | Path to OPA Rego policy file |
| `sarif` | No | — | SARIF file from an external analyzer to merge ([details](#authoritative-analysis-bring-your-own-scanner-sarif)) |
| `semgrep` | No | `false` | Run Semgrep automatically and merge its findings (ignored when `sarif` is set) |
| `semgrep-config` | No | `auto` | Semgrep ruleset when `semgrep: true` (registry ID or local rules file) |
| `ai-review` | No | — | Path(s) to AI reviewer verdict files, newline- or comma-separated ([details](#ai-review-verdicts-semantic-review-as-gate-input)) |
| `report` | No | `false` | Append an AI attribution digest to the summary/comment/artifact ([details](#periodic-ai-attribution-digest)) |
| `report-since` | No | `90 days ago` | History window for the attribution digest (any git `--since` expression) |
| `calibration` | No | `false` | Compute risk-tier calibration from merged PR outcomes labeled `ods:outcome/*` |
| `calibration-window-days` | No | `30` | Lookback window for calibration sampling |
| `calibration-min-samples` | No | `20` | Minimum labeled samples before tuning recommendations |
| `calibration-summary` | No | `false` | Append calibration summary to job summary / PR comment |
| `summary` | No | `true` | Append report to job summary |
| `comment` | No | `true` | Post/update PR comment |
| `review-routing` | No | `false` | Label the PR with its review tier; request reviewers for `elevated` ([details](#review-routing-spend-review-attention-where-it-matters)) |
| `elevated-reviewers` | No | — | Comma-separated usernames to request when the tier is `elevated` |
| `artifact` | No | `true` | Upload report as workflow artifact |
| `output-dir` | No | `ods-report` | Report output directory |
| `artifact-name` | No | `ods-report` | Uploaded artifact name |
| `artifact-retention-days` | No | `30` | Artifact retention period |
| `github-token` | No | `${{ github.token }}` | Token for PR comments |
| `cli-ref` | No | `v0.7.1` | ODS CLI version/tag/commit (`main` for latest) |

## Outputs

| Output | Description |
|--------|-------------|
| `result` | `pass` \| `warn` \| `block` |
| `ai-detected` | `true` \| `false` |
| `ai-confidence` | Detection confidence (0.0–1.0) |
| `tech-debt-delta` | Technical debt delta score |
| `policy-allowed` | `true` \| `false` |
| `review-tier` | `auto` \| `standard` \| `elevated` — the policy's review-routing verdict ([details](#review-routing-spend-review-attention-where-it-matters)) |

## Generated Artifacts

The uploaded artifact contains:

```text
ods-report/
├── index.html          (standalone HTML report)
├── ods-report.json     (machine-readable JSON)
├── ods-summary.md      (Markdown for job summary / PR comment)
├── ods-badge.svg       (badge showing result)
├── attribution.json    (only with report: true — raw ods report output)
└── ods-attribution.md  (only with report: true — rendered digest)
├── calibration.json    (only with calibration: true — confusion matrix + metrics)
└── ods-calibration.md  (only with calibration: true — rendered calibration summary)
```

> ODS always embeds a hidden `<!-- ods-calibration ... -->` marker in its PR
> comment so merged outcomes can be compared against prior predictions.

---

## Periodic AI Attribution Digest

Set `report: true` to append an **AI attribution digest** — AI vs human commit
and changed-line share over a window, with a per-tool breakdown — to the job
summary, the PR comment, and the artifact. It answers "how much of our delivery
is AI-assisted, and trending which way?"

```yaml
- uses: actions/checkout@v7
  with:
    fetch-depth: 0          # required: the digest reads git history
- uses: open-delivery-spec/validate-action@v1
  with:
    report: true
    report-since: "30 days ago"   # optional, defaults to 90 days
```

For a recurring org-wide digest, run it on a schedule and read it from the job
summary (no PR to comment on):

```yaml
on:
  schedule:
    - cron: "0 9 * * 1"     # Mondays 09:00 UTC
jobs:
  ai-digest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - uses: open-delivery-spec/validate-action@v1
        with:
          report: true
          comment: false
```

Like all detection in ODS, this is **attribution from `Co-Authored-By` trailers**
— what AI tools disclose, not forensic detection.

---

## Risk-Tier Calibration Loop (merge outcome feedback)

Enable `calibration: true` to compute how well ODS risk predictions align with
real merged outcomes in the same repository.

```yaml
- uses: open-delivery-spec/validate-action@v1
  with:
    calibration: true
    calibration-window-days: "30"
    calibration-min-samples: "20"
    calibration-summary: false
```

How feedback works:

1. ODS writes a hidden prediction marker into each PR comment (`ods-calibration`).
2. After merge, maintainers label the PR with an outcome:
   - `ods:outcome/clean` or `ods:outcome/low`
   - `ods:outcome/rework` or `ods:outcome/medium`
   - `ods:outcome/incident`, `ods:outcome/hotfix`, `ods:outcome/revert`, or `ods:outcome/high`
3. The calibration report builds a confusion matrix (predicted vs actual) and
   emits recommendations for tightening/relaxing routing thresholds.

This keeps risk routing honest over time: if high-risk recall drops, routing
gets stricter; if false alarms are too high, routing can be relaxed.

---

## Authoritative Analysis: Bring Your Own Scanner (SARIF)

ODS ships a handful of lightweight, intentionally conservative built-in
heuristics. They are **hints, not a verdict** — and they are strongest on Go.
For authoritative, multi-language analysis, point a dedicated scanner at your
code and feed its results to ODS via the `sarif` input. ODS merges those
findings into the analysis, the score, and the policy gate alongside its own.

Any tool that emits **SARIF v2.1.0** works — Semgrep, CodeQL, golangci-lint,
ESLint, Bandit, and more. ODS becomes the governance layer over the scanners
you already trust.

### Zero-setup: let the Action run Semgrep

Set `semgrep: true` and the Action installs and runs Semgrep for you, then
merges its findings — no extra steps:

```yaml
- uses: actions/checkout@v7
  with:
    fetch-depth: 0
- uses: open-delivery-spec/validate-action@v1
  with:
    semgrep: true
    # semgrep-config: p/ci   # optional: a registry ruleset or a local rules file
```

### Bring your own SARIF

Prefer to control the scan yourself (custom rules, caching, another tool)?
Produce a SARIF file in an earlier step and pass its path as `sarif:` — this
takes precedence over `semgrep:`.

```yaml
- uses: actions/checkout@v7
  with:
    fetch-depth: 0

- name: Run Semgrep
  run: |
    pip install semgrep
    # '|| true' so a non-zero scan result doesn't fail the step;
    # ODS decides pass/warn/block from the findings.
    semgrep --config auto --sarif --output semgrep.sarif || true

- uses: open-delivery-spec/validate-action@v1
  with:
    sarif: semgrep.sarif
```

The same pattern works with any scanner — produce a `.sarif` file in an earlier
step, then pass its path as `sarif:`. For example, golangci-lint
(`--out-format sarif`), ESLint (`@microsoft/eslint-formatter-sarif`), or Ruff
(`--output-format sarif`).

Findings carry their original rule IDs and severities (mapped to ODS
`critical`/`high`/`medium`/`low`/`info`), so your Rego policy can gate on them
just like built-in rules:

```rego
deny[msg] {
    issue := input.issues[_]
    issue.severity == "high"
    msg := sprintf("%s at %s:%d", [issue.rule, issue.file, issue.line])
}
```

---

## Enterprise Policy

Define custom enforcement rules in `.ods/policy.rego`:

```rego
package ods.policy

default allow := true

# Block critical issues unconditionally
deny[msg] {
    issue := input.issues[_]
    issue.severity == "critical"
    msg = sprintf("CRITICAL: %s at %s:%d", [issue.rule, issue.file, issue.line])
}

# Block high-confidence AI code with low test coverage
deny[msg] {
    input.ai_confidence > 0.8
    input.test_coverage < 0.3
    msg = "AI code with low test coverage"
}

# Block high tech debt delta
deny[msg] {
    input.technical_debt_delta > 5.0
    msg = sprintf("Technical debt increase %.1f exceeds threshold", [input.technical_debt_delta])
}

# Warn on high-confidence AI with quality issues
warn[msg] {
    input.ai_generated == true
    input.ai_confidence > 0.8
    count(input.issues) > 2
    msg = "High-confidence AI code with multiple quality issues"
}
```

Available policy input fields:

| Field | Type | Description |
|-------|------|-------------|
| `input.ai_generated` | bool | Whether AI code was detected |
| `input.ai_confidence` | float | Detection confidence (0.0–1.0) |
| `input.ai_files` | array | Per-file AI detection details |
| `input.issues` | array | Quality issues found |
| `input.technical_debt_delta` | float | Technical debt impact score |
| `input.test_coverage` | float | Test coverage ratio (0.0–1.0) |
| `input.branch` | string | Branch name |
| `input.changed_files` | array | Changed file paths in the diff |

---

## Review Routing: Spend Review Attention Where It Matters

The real bottleneck in AI-assisted delivery is not review speed — it is
attention allocation. Your policy can answer a second question beyond
allow/deny: **how much human attention does this PR need?** Define a
`review_tier` rule (`auto` / `standard` / `elevated`) in your Rego policy and
the action will surface and act on it:

```yaml
- uses: open-delivery-spec/validate-action@v1
  id: ods
  with:
    review-routing: "true"
    elevated-reviewers: "alice,bob"   # requested when tier = elevated
```

With `review-routing: true` the action labels the PR
(`ods:review/auto|standard|elevated`) and, for `elevated`, requests the
configured reviewers. Semantics: **deny always wins** — a blocked PR is never
routed; routing is advisory and never fails the run. Policies without a
`review_tier` rule default to `standard`.

The `auto` tier is deliberately **not** wired to merge anything. If you want
low-risk PRs to merge on their own, opt in explicitly with a follow-up step —
the gate has already passed by the time it runs (a blocked PR fails the job
before this step):

```yaml
- name: Auto-merge low-risk PRs
  if: steps.ods.outputs.review-tier == 'auto'
  env:
    GH_TOKEN: ${{ github.token }}
  run: gh pr merge --auto --squash "${{ github.event.pull_request.html_url }}"
```

Requires "Allow auto-merge" in the repository settings and branch protection
rules you trust. Merging is irreversible — that decision stays in your
workflow, not inside this action.

See the [CLI docs](https://github.com/open-delivery-spec/cli#review-routing-review_tier)
for the `review_tier` Rego contract and example rules.

---

## AI Review Verdicts: Semantic Review as Gate Input

Static analysis catches rule violations; an AI code reviewer judges whether
the change is *correct* — edge cases, logic, intent. The `ai-review` input
feeds those opinions into the policy gate without letting them take it over:

```yaml
- name: AI code review
  run: |
    # Any reviewer works — it just has to write a review-verdict/v1 file:
    # https://github.com/open-delivery-spec/spec/blob/main/schemas/review-verdict/v1.json
    your-ai-reviewer --output ai-review.json

- uses: open-delivery-spec/validate-action@v1
  with:
    ai-review: ai-review.json          # newline/comma-separated for several
    review-routing: "true"             # act on the elevated tier
```

The verdict file:

```json
{
  "schema": "ods.dev/review-verdict/v1",
  "reviewer": { "tool": "claude-code", "model": "claude-sonnet-4-5" },
  "head_sha": "${{ github.event.pull_request.head.sha }}",
  "verdict": "request_changes",
  "findings": [
    { "file": "src/auth.py", "line": 42, "severity": "high",
      "category": "correctness", "message": "expiry check uses local time" }
  ]
}
```

Semantics — the same principle as everywhere in ODS: **deterministic findings
may deny; probabilistic opinions only route attention.**

- A `request_changes` verdict raises the review tier to `elevated` (label +
  requested reviewers with `review-routing: true`) and adds a warning. It
  never fails the run.
- An `approve` never loosens the gate — it cannot qualify a PR for the `auto`
  tier. A prompt-injected or over-optimistic reviewer can cost you a little
  extra review attention, never a bad merge.
- Teams that want AI findings to block opt in explicitly in their own Rego
  over `input.ai_reviews` — see the
  [CLI docs](https://github.com/open-delivery-spec/cli#ai-reviewer-verdicts---ai-review).
- Verdicts stamped with a `head_sha` that doesn't match the PR head are
  skipped as stale (the action sets `ODS_HEAD_SHA` from the event, so this
  works on `pull_request` merge-commit checkouts too). Malformed files are
  skipped with a warning.

The verdicts render as an **AI Review** section in the PR comment and job
summary, and are preserved in the report artifact as audit evidence.

---

## Disabling Surfaces

Turn off specific display surfaces when you only want validation:

```yaml
- uses: open-delivery-spec/validate-action@v1
  with:
    summary: "false"
    comment: "false"
    artifact: "false"
```

---

## Manual PR Body

If your workflow doesn’t have access to `github.event.pull_request.body`:

```yaml
- uses: open-delivery-spec/validate-action@v1
  with:
    pr-body: |
      ## AI Disclosure
      - [x] This PR contains AI-generated code
      - AI Tool: GitHub Copilot
```

---

## In Production

This Action runs on every PR in the `open-delivery-spec` org (dogfooding) and in external repositories including [devops-maturity](https://github.com/devops-maturity/devops-maturity) and [conventional-branch](https://github.com/conventional-branch/conventional-branch). See [ADOPTERS.md](https://github.com/open-delivery-spec/spec/blob/main/ADOPTERS.md) for the current list.

---

## License

[Apache License 2.0](LICENSE)
