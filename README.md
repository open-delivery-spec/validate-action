# ODS Validate Action

[![ODS Validate](https://github.com/open-delivery-spec/validate-action/actions/workflows/ods-validate.yml/badge.svg)](https://github.com/open-delivery-spec/validate-action/actions/workflows/ods-validate.yml)
[![CI](https://github.com/open-delivery-spec/validate-action/actions/workflows/self-test.yml/badge.svg)](https://github.com/open-delivery-spec/validate-action/actions/workflows/self-test.yml)

> **AI code quality gate for CI.** Detect AI-generated code, analyze quality defects, score technical debt impact, and enforce enterprise policy — on every pull request.

---

## Why ODS?

AI writes code faster than ever, but AI code increases technical debt in predictable ways:

| AI Failure Mode | Real-world impact |
|---|---|
| **Hallucinated APIs** | AI invents functions, packages, endpoints that don't exist |
| **Redundant error handling** | 3+ identical `if err != nil` blocks in the same function |
| **Over-commenting** | 35%+ comment-to-code ratio with self-explanatory comments |
| **Missing tests** | AI PRs average 22% test coverage vs 68% for human PRs |
| **Invisible AI code** | Teams can't distinguish AI-generated from human-written changes |

This Action runs the full ODS pipeline on every PR so low-quality AI code never reaches production.

---

## Quick Start

```yaml
name: ODS AI Code Quality
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  ods:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0  # required for git diff against base
      - uses: open-delivery-spec/validate-action@v1
```

That's it. The Action automatically:

1. **Detects** AI-generated code (commit trailers, PR disclosure, branch names, diff heuristics)
2. **Analyzes** code quality (5 rule categories for AI-specific defects)
3. **Scores** technical debt impact (5-dimension weighted model)
4. **Enforces** policy (OPA Rego — optional, place at `.ods/policy.rego`)

---

## What You'll See

### PR Comment (auto-posted)

> ## ODS AI Code Quality Report
>
> **Result:** ✅ PASS  
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

> **Result:** ⚠️  WARN  
> **AI Detected:** 🤖 Yes (confidence: 85%)  
> **Tech Debt Delta:** +4.2 (increase)  
> **Policy:** ✅ Allowed  
>
> ### 🔍 Detection
> | Source | Signal | Confidence |
> |--------|--------|-----------|
> | pr-body | AI disclosure checkbox is checked | 85% |
>
> ### 📊 Analysis
> 3 issue(s) found: 1 high, 2 medium
> ...

### When policy blocks the PR:

> **Result:** ❌ BLOCK  
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
> **Note:** `diff-base` currently only affects the `detect` step. The `analyze`, `score`, and `check` steps always use `HEAD~1`. This will be unified in a future release.
| `policy` | No | `.ods/policy.rego` | Path to OPA Rego policy file |
| `summary` | No | `true` | Append report to job summary |
| `comment` | No | `true` | Post/update PR comment |
| `artifact` | No | `true` | Upload report as workflow artifact |
| `output-dir` | No | `ods-report` | Report output directory |
| `artifact-name` | No | `ods-report` | Uploaded artifact name |
| `artifact-retention-days` | No | `30` | Artifact retention period |
| `github-token` | No | `${{ github.token }}` | Token for PR comments |
| `cli-ref` | No | `main` | ODS CLI version/tag/commit |

## Outputs

| Output | Description |
|--------|-------------|
| `result` | `pass` \| `warn` \| `block` |
| `ai-detected` | `true` \| `false` |
| `ai-confidence` | Detection confidence (0.0–1.0) |
| `tech-debt-delta` | Technical debt delta score |
| `policy-allowed` | `true` \| `false` |

## Generated Artifacts

The uploaded artifact contains:

```text
ods-report/
├── index.html          (standalone HTML report)
├── ods-report.json     (machine-readable JSON)
├── ods-summary.md      (Markdown for job summary / PR comment)
└── ods-badge.svg       (badge showing result)
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
| `input.changed_files` | array | Changed file paths _(not yet populated — planned)_ |

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

If your workflow doesn't have access to `github.event.pull_request.body`:

```yaml
- uses: open-delivery-spec/validate-action@v1
  with:
    pr-body: |
      ## AI Disclosure
      - [x] This PR contains AI-generated code
      - AI Tool: GitHub Copilot
```

---

## License

[Apache License 2.0](LICENSE)
