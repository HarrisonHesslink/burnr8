# Release burnr8

Run the full release pipeline for version `$ARGUMENTS`.

## Pre-flight

1. Close PR #78 or any stale release PRs if they exist
2. Switch to `main` and pull latest: `git checkout main && git pull origin main`
3. Verify working tree is clean: `git status --porcelain` must be empty
4. Verify the version in `pyproject.toml` does NOT already match `$ARGUMENTS` — if it does, skip to **Phase 2**

## Phase 1: Version bump PR

The release script handles this. Run:

```bash
./scripts/release.sh $ARGUMENTS
```

This will:
- Run full local CI (lint, typecheck, unit tests, integration tests if creds available, import check, CVE scan, build check)
- Bump version in all 6 files (pyproject.toml, __init__.py fallback, marketplace.json, plugin.json x2, SKILL.md)
- Create a release branch and PR
- Exit after PR creation

After the script creates the PR:
1. Report the PR URL to the user
2. **STOP and wait** — tell the user to merge the PR
3. Do NOT proceed to Phase 2 until the user confirms the PR is merged

## Phase 2: Tag and release

After the user confirms the PR is merged:

1. Switch to main and pull: `git checkout main && git pull origin main`
2. Verify the version in `pyproject.toml` matches `$ARGUMENTS`
3. Run the release script again:

```bash
./scripts/release.sh $ARGUMENTS
```

This second run detects the version already matches and:
- Creates git tag `v$ARGUMENTS`
- Pushes the tag
- Creates a GitHub Release with auto-generated notes

4. Report the release URL to the user
5. Remind them to check GitHub Actions for PyPI + Docker publish status

## Error handling

- If local CI fails, report which step failed and stop. Do not bypass CI.
- If the semgrep pre-push hook fails with `ModuleNotFoundError: No module named 'pkg_resources'`, this is a known issue with the cached semgrep env. Use `SKIP=semgrep git push` for the release branch push only.
- If `git tag` fails because the tag exists, the script handles cleanup automatically.

## Workflow rules

- Never skip CI checks
- Never force-push
- Always wait for user to merge the PR before tagging
- The release script is the source of truth — don't manually bump versions or create tags outside it
