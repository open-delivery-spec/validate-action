# ODS Validate Action

[![ODS Validate](https://github.com/open-delivery-spec/validate-action/actions/workflows/ods-validate.yml/badge.svg)](https://github.com/open-delivery-spec/validate-action/actions/workflows/ods-validate.yml)
[![CI](https://github.com/open-delivery-spec/validate-action/actions/workflows/self-test.yml/badge.svg)](https://github.com/open-delivery-spec/validate-action/actions/workflows/self-test.yml)

> **Zero-config governance and visibility for AI-assisted code — on every pull request.** Claude Code, Copilot, and Cursor already stamp `Co-Authored-By` trailers on every commit, so ODS shows how much of your delivery is AI-assisted, routes review attention to the changes that need it, and enforces your policy in CI — no disclosure forms, no manual tagging. It governs the AI you can see; it's a signal producer, not a quality oracle.

---

## Why ODS?

AI-assisted changes arrive faster than review attention grows, and most teams
cannot say which changes were AI-assisted, whether they were tested, or whether
they met the team's rules. This Action answers those questions on every pull
request and enforces the answer as policy. The full argument, the detection
signals and their confidence, and the design principles are in the
[spec README](https://github.com/open-delivery-spec/spec#readme).

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

> `fetch-depth: 0` is **required for accurate results** — ODS's diff- and
> history-based signals need the base commit and commit history. If you forget
> it, the Action detects the shallow checkout at runtime and warns in the logs
> and the PR report with the exact fix, instead of quietly reporting on partial
> inputs.

> Keep the checkout's default ref (the merge commit) or check out
> `github.event.pull_request.head.sha`. Do **not** use `ref: ${{ github.head_ref }}`:
> that branch exists only in the contributor's fork, so the checkout itself
> fails on fork pull requests — see
> [Permissions and Fork Pull Requests](#permissions-and-fork-pull-requests).

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
> stable release** of the ODS CLI (`cli-ref: v0.7.8`) so runs are reproducible.
> To always track the latest detection and analysis improvements, set it to
> `main` (or any tag/commit):
>
> ```yaml
> - uses: open-delivery-spec/validate-action@v1
>   with:
>     cli-ref: main   # latest; or a specific tag/commit like v0.7.8
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

One comment per pull request, updated in place. The badge answers *"does this
need a human?"*, and every reason it is not green is named in a **Why** line:

> **Result:** ⚠️  WARN  
> **AI Detected:** 🤖 Yes (confidence: 90%)  
> **Evidence:** 🟡 attested  
> **Tech Debt Delta:** +0.4 (low risk)  
> **Policy:** ✅ Allowed  
> **Review Tier:** 🟠 elevated  
> **Why:** 1 policy warning; policy routed this to elevated review  
>
> ### 🔍 Detection
> | Source | Signal | Confidence |
> |--------|--------|------------|
> | commit-trailer | AI-assisted commit 3f2a9c1 (tool: Claude) | 90% |
>
> ### ⚠️  Policy Warnings
> - ⚠️  AI-authored change: only 41% of added lines are covered by tests

AI involvement on its own is never a finding: a clean, disclosed AI-authored
change passes. Every number names its provenance (`AI Code Ratio: 60% (from
attributed commits)`) or reads `N/A (not measured)`; nothing is derived from the
detection confidence. The comment and the report artifact are produced for
every result, `BLOCK` included: the job fails, and the PR still carries the
report that explains why. Every pull request in this repository carries a live
example.

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
| `mutation-report` | No | — | Path to a mutation-testing report (gremlins JSON); its diff-scoped mutation score feeds the gate |
| `failure-mode` | No | `warn` | What to do when a stage (detect/analyze/score/check) fails to produce a result: `warn` (never report a broken stage as a clean pass) or `block` (fail the run — fail-closed) |
| `report` | No | `false` | Append an AI attribution digest to the summary/comment/artifact ([details](#periodic-ai-attribution-digest)) |
| `report-since` | No | `90 days ago` | History window for the attribution digest (any git `--since` expression) |
| `summary` | No | `true` | Append report to job summary |
| `comment` | No | `true` | Post/update PR comment |
| `review-routing` | No | `false` | Label the PR with its review tier; request reviewers for `elevated` ([details](#review-routing-spend-review-attention-where-it-matters)) |
| `elevated-reviewers` | No | — | Comma-separated usernames to request when the tier is `elevated` |
| `artifact` | No | `true` | Upload report as workflow artifact |
| `output-dir` | No | `ods-report` | Report output directory |
| `artifact-name` | No | `ods-report` | Uploaded artifact name |
| `artifact-retention-days` | No | `30` | Artifact retention period |
| `github-token` | No | `${{ github.token }}` | Token for PR comments |
| `cli-ref` | No | `v0.7.8` | ODS CLI version/tag/commit (`main` for latest) |

## Outputs

| Output | Description |
|--------|-------------|
| `result` | `pass` \| `warn` \| `block` — `block` when the policy denied the change (or a stage failed under `failure-mode: block`); `warn` when the policy warned or routed to elevated review, or the pipeline could not answer; `pass` otherwise. Detected AI alone never produces a `warn` |
| `ai-detected` | `true` \| `false` |
| `ai-confidence` | Detection confidence (0.0–1.0) |
| `tech-debt-delta` | Technical debt delta score |
| `policy-allowed` | `true` \| `false` |
| `review-tier` | `auto` \| `standard` \| `elevated` — the policy's review-routing verdict ([details](#review-routing-spend-review-attention-where-it-matters)) |
| `pipeline-integrity` | `ok` \| `inconclusive` — whether every stage (detect, analyze, score, check) produced a result; `inconclusive` reports as `warn`, or `block` under `failure-mode: block` |

## Generated Artifacts

The uploaded artifact contains:

```text
ods-report/
├── index.html          (standalone HTML report)
├── ods-report.json     (machine-readable JSON)
├── ods-summary.md      (Markdown for job summary / PR comment)
├── ods-badge.svg       (badge showing result)
├── evidence.cdx.json   (AI-code evidence document — a CycloneDX 1.6 BOM attesting what the gate evaluated; needs a CLI with `ods attest`)
├── attribution.json    (only with report: true — raw ods report output)
└── ods-attribution.md  (only with report: true — rendered digest)
```

---

## Periodic AI Attribution Digest

Set `report: true` to append an **AI attribution digest** — AI vs human commit
and changed-line share over a window, with a per-tool breakdown — to the job
summary, the PR comment, and the artifact. It answers "how much of our delivery
is AI-assisted, and trending which way?"

With a CLI that supports it (v0.7.2+), the step also drops a self-contained,
shareable **HTML dashboard** (`ai-attribution.html` — hero metrics, an "AI share
over time" trend chart, per-tool bars) into the report artifact, and the PR
comment points to it.

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

For every repository in the organization at once, use the
[`org-ai-report`](https://github.com/open-delivery-spec/.github/blob/main/.github/workflows/org-ai-report.yml)
reusable workflow: it scans the repositories on a schedule, merges them with
`ods report merge`, and publishes one dashboard as an artifact, a job summary,
or GitHub Pages. See [Organization-wide View](https://open-delivery-spec.github.io/spec/org-view.html).

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

Put your rules in `.ods/policy.rego` and the Action enforces them; without one,
the CLI's built-in default applies (deny only critical findings, warn and route
everything else). A minimal policy:

```rego
package ods.policy

default allow := true

# Block critical findings unconditionally
deny[msg] {
    issue := input.issues[_]
    issue.severity == "critical"
    msg = sprintf("CRITICAL: %s at %s:%d", [issue.rule, issue.file, issue.line])
}

# Block high-confidence AI code with low test coverage.
# test_coverage is -1 when no coverage report was found: guard with >= 0.
deny[msg] {
    input.ai_confidence > 0.8
    input.test_coverage >= 0
    input.test_coverage < 0.3
    msg = "AI code with low test coverage"
}
```

Every field the policy can read, with its sentinels, is in the
[Policy Input Schema](https://open-delivery-spec.github.io/spec/schemas.html);
the patterns (warn first, route with `review_tier`, opt-in denies over
probabilistic signals) are in
[Writing Policies (Rego)](https://open-delivery-spec.github.io/spec/policy-authoring.html),
and ready-made templates for open-source and enterprise repositories are in
[`examples/`](https://github.com/open-delivery-spec/spec/tree/main/examples).

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
feeds those opinions into the policy gate without letting them take it over.

**Get started in one job** with the reference recipe in
[`examples/ai-review/`](examples/ai-review/) — a prompt plus a tolerant
normalizer (`scripts/to-verdict.py`) that turns any LLM's best-effort output
into a schema-valid verdict. Bring your own model and key:

```yaml
- name: AI code review
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  run: |
    git diff origin/${{ github.base_ref }}...HEAD > pr.diff
    claude -p "$(cat examples/ai-review/review-prompt.md)" < pr.diff > raw.txt || true
    python3 scripts/to-verdict.py raw.txt --tool claude-code \
      --head-sha "${{ github.event.pull_request.head.sha }}" --out ai-review.json

- uses: open-delivery-spec/validate-action@v1
  with:
    ai-review: ai-review.json          # newline/comma-separated for several
    review-routing: "true"             # act on the elevated tier
```

Any reviewer works — it just has to emit a `review-verdict/v1` file. Swap the
review step for CodeRabbit, Copilot code review, or your own converter.

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

## Permissions and Fork Pull Requests

Two surfaces write to the pull request and need `pull-requests: write` on the
workflow's `GITHUB_TOKEN`: the **PR comment** and **review routing** (labels,
reviewer requests). Everything else — the gate itself, the check result, the
job summary, and the report artifact — works with a read-only token.

GitHub gives `pull_request` workflows triggered **from a fork** a read-only
token, whatever the workflow's `permissions` block says. On those PRs the
Action still runs the full pipeline and still fails the check on `BLOCK`, but
it cannot post the comment or apply labels. The log names the fork when that
happens, and the report is in the job summary and the `ods-report` artifact.

Two things keep fork pull requests working:

1. **Check out the PR head by SHA, or keep the default merge ref.**
   `ref: ${{ github.head_ref }}` is a branch name that exists only in the
   fork, so the checkout itself fails on fork PRs:

   ```yaml
   - uses: actions/checkout@v7
     with:
       fetch-depth: 0
       ref: ${{ github.event.pull_request.head.sha }}   # resolves for forks too
   ```

2. **To comment on fork PRs, post from a follow-up `workflow_run` job.** It
   runs in the base repository with a write token, reads the report the gate
   uploaded (the artifact is uploaded on every result, `BLOCK` included), and
   never checks out fork code:

   ```yaml
   # .github/workflows/ods-comment.yml
   name: ODS PR comment
   on:
     workflow_run:
       workflows: ["ODS AI Code Quality"]   # the workflow that runs validate-action
       types: [completed]

   permissions:
     actions: read
     pull-requests: write

   jobs:
     comment:
       if: github.event.workflow_run.event == 'pull_request'
       runs-on: ubuntu-latest
       steps:
         - uses: actions/download-artifact@v8
           with:
             name: ods-report
             path: ods-report
             run-id: ${{ github.event.workflow_run.id }}
             github-token: ${{ github.token }}
         - name: Post or update the ODS comment
           env:
             GH_TOKEN: ${{ github.token }}
             HEAD_SHA: ${{ github.event.workflow_run.head_sha }}
             RUN_URL: ${{ github.event.workflow_run.html_url }}
           run: |
             set -euo pipefail
             PR=$(gh api "repos/${GITHUB_REPOSITORY}/commits/${HEAD_SHA}/pulls" --jq '.[0].number // empty')
             [ -n "$PR" ] || { echo "No pull request found for ${HEAD_SHA}"; exit 0; }
             { cat ods-report/ods-summary.md; echo; echo "[View workflow run](${RUN_URL})"; } > body.md
             ID=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR}/comments?per_page=100" \
                    --jq '[.[] | select(.body | contains("<!-- ods-compliance-report -->"))][0].id // empty')
             if [ -n "$ID" ]; then
               gh api -X PATCH "repos/${GITHUB_REPOSITORY}/issues/comments/${ID}" -F body=@body.md >/dev/null
             else
               gh api -X POST "repos/${GITHUB_REPOSITORY}/issues/${PR}/comments" -F body=@body.md >/dev/null
             fi
   ```

   Set `comment: "false"` on the gate workflow when you use this, so the two
   never race on same-repository PRs.

`pull_request_target` also gets a write token, but it runs your workflow with
that token against untrusted fork code. Prefer the `workflow_run` pattern above.

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
