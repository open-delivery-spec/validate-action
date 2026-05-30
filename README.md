# ODS Validate Action

[![CI](https://github.com/open-delivery-spec/validate-action/actions/workflows/self-test.yml/badge.svg)](https://github.com/open-delivery-spec/validate-action/actions/workflows/self-test.yml)

GitHub Action to validate delivery artifacts against [Open Delivery Spec](https://github.com/open-delivery-spec/spec) standards with configurable compliance policies.

- `branch-naming`
- `commit-message`
- `pr-description`
- `all`

Draft checks for AI review, CI failure, release readiness, approval workflow, rollback plans, and production evidence are intentionally not enforced by this Action yet. Use the ODS CLI `validate` commands directly when experimenting with draft module schemas.

## Quick Start

### Pull Request L1 Check

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

### Policy Profiles

Choose a compliance policy that matches your organization's needs:

| Profile | AI Disclosure | Commit Scope | Tickets | Best For |
|---------|:---:|:---:|:---:|---|
| `oss` | Optional | Optional | No | Open-source projects |
| `enterprise` _(default)_ | Required | Required | No | Most teams |
| `regulated` | Required | Required | Yes | Finance, healthcare, gov |

```yaml
- uses: open-delivery-spec/validate-action@v1
  with:
    check: all
    profile: enterprise  # or oss, regulated
```

Or configure fine-grained rules via a `.ods.yaml` in your repository root. See [examples/ods-policy-oss.yaml](https://github.com/open-delivery-spec/spec/blob/main/examples/ods-policy-oss.yaml) and [examples/ods-policy-regulated.yaml](https://github.com/open-delivery-spec/spec/blob/main/examples/ods-policy-regulated.yaml).

### Fix Suggestions (PR Comments)

When checks fail, the action automatically generates **copy-paste fix templates** in the PR comment. Developers see exactly what to fix:

```markdown
## 🔧 Fix Suggestions

### Branch naming
**1. Use a valid branch type**
Replace 'feat' with one of: feature, bugfix, hotfix, release, chore
```
feature/add-oauth-login
```

### PR description
**1. Add missing PR sections**
Your PR is missing 2 required section(s).
```
## AI Disclosure
- [ ] This PR contains AI-generated code
...
```
```

`all` reports any stable L1 context available from explicit inputs, the GitHub event payload, or local git metadata. In the example above, branch naming and PR description are supplied directly.

By default the action also publishes the compliance result in three places:

- Pull request comment: one `ODS Compliance Report` comment is created and updated on later runs, with fix suggestions when applicable.
- GitHub Actions summary: `ods-summary.md` is appended to the job summary, with fix suggestions.
- Workflow artifact: the full report directory is uploaded as `ods-compliance-report` with an enhanced HTML dashboard.

The generated artifact contains:

```text
ods-report/
├── index.html
├── ods-compliance.json
├── ods-compliance.svg
└── ods-summary.md
```

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
| `profile` | No | `enterprise` | Compliance profile: `oss`, `enterprise`, or `regulated` |
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
