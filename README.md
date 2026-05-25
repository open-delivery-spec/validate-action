# ODS GitHub Action

[![CI](https://github.com/open-delivery-spec/validate-action/actions/workflows/self-test.yml/badge.svg)](https://github.com/open-delivery-spec/validate-action/actions/workflows/self-test.yml)

GitHub Action for the production-ready ODS M1 checks:

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

`all` runs only the M1 checks that have input. In the example above, it validates branch naming and PR description. It skips commit-message validation because pull request events do not expose a single canonical commit message.

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

Reserved inputs such as `pr_number`, `review_record`, `release_version`, `rollback_plan`, and `evidence_bundle` are present for forward compatibility but are not enforced by M1 checks.

## Outputs

| Output | Description |
|--------|-------------|
| `result` | `conformant`, `conformant-with-warnings`, or `non-conformant` |

## License

[Apache License 2.0](LICENSE)
