# ODS Validate Action

[![CI](https://github.com/open-delivery-spec/validate-action/actions/workflows/self-test.yml/badge.svg)](https://github.com/open-delivery-spec/validate-action/actions/workflows/self-test.yml)
[![ODS L1](https://img.shields.io/badge/ODS-L1%20Structured%20Delivery-blue)](https://github.com/open-delivery-spec/spec)

> **Dogfooding:** This Action validates its own PRs using the ODS L1 checks. Every release is ODS-compliant.

**The fastest way to adopt Open Delivery Spec.** Install this Action and get structured PR validation, AI disclosure enforcement, and compliance reports in 5 minutes.

---

## Why ODS?

| Before ODS | After ODS |
|---|---|
| `Title: fix stuff` | `fix(auth): handle expired OAuth state parameter` |
| Empty PR body | Summary, Changes, Testing, AI Disclosure |
| "What does this do? Was it tested? Did AI write this?" | Reviewer has answers before opening the PR |
| No CI validation of PR metadata | CI blocks merges with missing sections |
| No visibility into AI-generated code | Machine-checkable AI disclosure on every PR |

> **ODS does not prove the code is correct.** It proves the delivery process has the minimum structured evidence for humans and machines to review the change responsibly.

---

- `branch-naming`
- `commit-message`
- `pr-description`
- `all`

Draft checks for AI review, CI failure, release readiness, approval workflow, rollback plans, and production evidence are intentionally not enforced by this Action yet. Use the ODS CLI `validate` commands directly when experimenting with draft module schemas.

## Pull Request L1 Check

```yaml
name: ODS L1
on:
  pull_request:
    types: [opened, edited, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write
  issues: write

jobs:
  ods:
    runs-on: ubuntu-latest
    steps:
      - uses: open-delivery-spec/validate-action@v1
        with:
          check: all
          branch_name: ${{ github.head_ref }}
          pr_body: ${{ github.event.pull_request.body }}
          strict: "true"
```

`all` reports any stable L1 context available from explicit inputs, the GitHub event payload, or local git metadata. In the example above, branch naming and PR description are supplied directly.

By default the action also publishes the compliance result in three places:

- Pull request comment: one `ODS Compliance Report` comment is created and updated on later runs.
- GitHub Actions summary: `ods-summary.md` is appended to the job summary.
- Workflow artifact: the full report directory is uploaded as `ods-compliance-report`.

The generated artifact contains:

```text
ods-report/
├── index.html              (standalone HTML report)
├── ods-compliance.json     (machine-readable JSON)
├── ods-compliance.svg      (badge for README)
├── ods-summary.md          (Markdown for job summary)
└── ods-compliance.sarif    (SARIF v2.1.0 for code scanning)
```

### What You'll See

**Passing PR — ODS bot comment:**

> ## ODS Compliance Report
>
> Status: ✅ ODS L1 Compliant  
> Score: 100 / 100  
> Profile: L1 - AI-aware delivery metadata  
>
> | Check | Result | Notes |
> |---|---|---|
> | Branch naming | ✅ Pass | feature/add-oauth-login |
> | Commit message | ✅ Pass | feat(auth): add OAuth login flow |
> | PR description | ✅ Pass | - |
>
> [View workflow run](https://github.com/...)

**Failing PR — ODS bot comment with fix guidance:**

> ## ODS Compliance Report
>
> Status: ❌ ODS L1 Non-Compliant  
> Score: 33 / 100  
> Profile: L1 - AI-aware delivery metadata  
>
> | Check | Result | Notes |
> |---|---|---|
> | Branch naming | ✅ Pass | bugfix/fix-token-expiry |
> | Commit message | ❌ Fail | fix stuff |
> | PR description | ❌ Fail | missing section: AI Disclosure; missing section: Risk Assessment |
>
> [View workflow run](https://github.com/...)

## Commit Message Check

```yaml
name: ODS Commit Message
on: [push]

jobs:
  commit-check:
    runs-on: ubuntu-latest
    steps:
      - uses: open-delivery-spec/validate-action@v1
        with:
          check: commit-message
          commit_message: ${{ github.event.head_commit.message }}
          strict: "true"
```

## Individual Checks

### Branch Naming

```yaml
- uses: open-delivery-spec/validate-action@v1
  with:
    check: branch-naming
    branch_name: ${{ github.head_ref }}
```

### PR Description

```yaml
- uses: open-delivery-spec/validate-action@v1
  with:
    check: pr-description
    pr_body: ${{ github.event.pull_request.body }}
```

### Commit Message

```yaml
- uses: open-delivery-spec/validate-action@v1
  with:
    check: commit-message
    commit_message: ${{ github.event.head_commit.message }}
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `check` | Yes | `all` | `branch-naming`, `commit-message`, `pr-description`, or `all` |
| `branch_name` | For `branch-naming` | - | Branch name to validate |
| `commit_message` | For `commit-message` | - | Commit message to validate |
| `pr_body` | For `pr-description` | - | PR description body |
| `strict` | No | `false` | Fail on warnings as well as errors |
| `spec_version` | No | `1.0.0` | Reserved for future spec-version selection |
| `profile` | No | `l1` | Reserved for future profile selection |
| `report` | No | `html` | Reserved for future report format selection |
| `summary` | No | `true` | Append Markdown report to the GitHub Actions job summary |
| `comment` | No | `true` | Create or update one ODS PR comment |
| `artifact` | No | `true` | Upload the generated report directory |
| `output-dir` | No | `ods-report` | Directory for generated report files |
| `artifact-name` | No | `ods-compliance-report` | Uploaded artifact name |
| `artifact-retention-days` | No | `30` | Uploaded artifact retention period |
| `github-token` | No | `${{ github.token }}` | Token used for PR comments |
| `cli-ref` | No | `main` | ODS CLI version, tag, or commit to install |

Reserved inputs such as `pr_number`, `review_record`, `release_version`, `rollback_plan`, and `evidence_bundle` are present for forward compatibility but are not enforced by M1 checks.

Disable display surfaces when you only want validation:

```yaml
- uses: open-delivery-spec/validate-action@v1
  with:
    check: all
    summary: "false"
    comment: "false"
    artifact: "false"
```

## Outputs

| Output | Description |
|--------|-------------|
| `result` | `conformant`, `conformant-with-warnings`, or `non-conformant` |

## License

[Apache License 2.0](LICENSE)
