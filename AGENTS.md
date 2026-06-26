# Agent Development Rules — open-delivery-spec/validate-action

This file instructs AI coding agents (Claude Code, Copilot Workspace, etc.) on how to work in this repository.

## About This Repo

This is the ODS GitHub Action. It wraps the `ods` CLI and exposes it as a reusable composite action for GitHub workflows.

- `action.yml` — action definition and inputs/outputs
- `scripts/` — shell scripts used by the action steps
- `test-fixtures/` — sample inputs used in integration tests

The action is published under the `v1` tag, which is kept pointing to the latest release via `.github/workflows/move-major-tag.yml`.

## Branching Rules

- **NEVER push directly to `main`.** All changes enter via pull request only.
- **Always start from the latest `main`.** Before creating any branch:

  ```bash
  git fetch origin
  git checkout main
  git pull origin main
  git checkout -b <branch-name>
  ```

  Never branch from a stale local `main` or from another feature branch.

- **Branch names must follow [Conventional Branch](https://conventional-branch.github.io/) naming.** Allowed prefixes:

  | Prefix | Use for |
  |--------|---------|
  | `feature/` | New action inputs, outputs, or steps |
  | `bugfix/` | Bug fixes in scripts or action logic |
  | `hotfix/` | Urgent fixes |
  | `release/` | Release preparation |
  | `chore/` | Dependency bumps, maintenance, **docs, CI, test fixtures, refactors** |

  AI-agent branches are also accepted: `claude/`, `copilot/`, `cursor/`, `github-actions/`

  Long-lived branches: `main`, `master`, `develop`

  Branch names must be lowercase. The description part must not contain `/`.

  > ⚠️ **Conventional _Branch_ types ≠ Conventional _Commit_ types.** Branch names use
  > `feature/bugfix/hotfix/release/chore`; commit messages use `feat/fix/docs/test/…`.
  > `test/`, `feat/`, `fix/`, `docs/`, `ci/` are **not** valid branch prefixes and are
  > rejected by `commit-check`. For docs/test/CI work, branch under `chore/`.

## Commit Message Rules

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/). This is enforced in CI by `commit-check`.

```
type(scope): description
```

- **type**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`, `revert`
- **scope**: optional, lowercase, no slashes (e.g., `action`, `scripts`, `inputs`)
- **description**: imperative mood, no capital first letter, no trailing period
- **subject line**: maximum 80 characters

Examples:
```
feat: add sarif-file input for SARIF result ingestion
fix(scripts): handle missing coverage file gracefully
chore: bump validate-action to use cli v0.3.0
ci: add integration test against test-fixtures
```

## Action Changes

When modifying `action.yml`:

- Keep inputs and outputs in sync with the `ods` CLI flags they map to
- Document every new input with a `description` and sensible `default`
- Update `README.md` usage examples when inputs/outputs change

When modifying scripts in `scripts/`:

- Scripts must be POSIX-compatible (`#!/bin/sh`, not `#!/bin/bash`) unless bash features are strictly required
- Validate inputs early and fail with a clear error message

## PR Workflow

- Ensure your branch is rebased on the latest `main` before opening a PR (`git rebase origin/main`)
- Do not open PRs without explicit user instruction
- All PRs target `main`
- CI runs `commit-check` (branch + message) and the ODS validate-action quality gate (self-dogfooding)
