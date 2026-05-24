# ODS GitHub Action

[![CI](https://github.com/open-delivery-spec/github-action/actions/workflows/self-test.yml/badge.svg)](https://github.com/open-delivery-spec/github-action/actions/workflows/self-test.yml)

GitHub Action to validate delivery artifacts against [Open Delivery Spec](https://github.com/open-delivery-spec/spec) standards.

## Usage

### Branch Naming Check

```yaml
name: ODS Branch Naming
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  branch-check:
    runs-on: ubuntu-latest
    steps:
      - uses: open-delivery-spec/github-action@v1
        with:
          check: branch-naming
          branch_name: ${{ github.head_ref }}
```

### Commit Message Check

```yaml
name: ODS Commit Message
on: [push, pull_request]

jobs:
  commit-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: open-delivery-spec/github-action@v1
        with:
          check: commit-message
          commit_message: ${{ github.event.head_commit.message }}
```

### PR Description Check

```yaml
name: ODS PR Description
on:
  pull_request:
    types: [opened, edited]

jobs:
  pr-check:
    runs-on: ubuntu-latest
    steps:
      - uses: open-delivery-spec/github-action@v1
        with:
          check: pr-description
          pr_body: ${{ github.event.pull_request.body }}
```

### AI Review Check

```yaml
name: ODS AI Review
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  ai-review-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: open-delivery-spec/github-action@v1
        with:
          check: ai-review
          pr_number: ${{ github.event.pull_request.number }}
```

### Release Readiness Check

```yaml
name: ODS Release Readiness
on:
  release:
    types: [published]

jobs:
  release-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: open-delivery-spec/github-action@v1
        with:
          check: release-readiness
          release_version: ${{ github.ref_name }}
```

### All Checks

```yaml
name: ODS All Checks
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  ods-all:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: open-delivery-spec/github-action@v1
        with:
          check: all
          pr_number: ${{ github.event.pull_request.number }}
          strict: 'true'
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `check` | Yes | `all` | Check type: `branch-naming`, `commit-message`, `pr-description`, `ai-review`, `ci-failure`, `release-readiness`, `approval-workflow`, `rollback-plan`, `prod-evidence`, `all` |
| `branch_name` | For `branch-naming` | — | Branch name to validate |
| `commit_message` | For `commit-message` | — | Commit message to validate |
| `pr_body` | For `pr-description` | — | PR description body |
| `pr_number` | For `ai-review`, `approval-workflow` | — | PR number |
| `rollback_plan` | For `rollback-plan` | — | Path to rollback plan JSON file |
| `evidence_bundle` | For `prod-evidence` | — | Path to evidence bundle JSON file |
| `release_version` | For `release-readiness` | — | Release version |
| `strict` | No | `false` | Fail on warnings too |

## Outputs

| Output | Description |
|--------|-------------|
| `result` | `conformant`, `conformant-with-warnings`, or `non-conformant` |
| `score` | Release readiness score (0-100) |
| `details` | JSON validation details |

## License

[Apache License 2.0](LICENSE)
