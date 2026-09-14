# Contributing

## Branches and integration

We use a lightweight feature-branch workflow. `main` is the integration branch;
published versions are identified by release tags. There is no permanent
`develop` branch. Start each independent change from the latest `main` and merge
through a pull request rather than committing directly to `main`.

Use short, descriptive branch names:

- `codex/feat-<topic>` for features
- `codex/fix-<topic>` for fixes
- `codex/docs-<topic>` for documentation
- `codex/chore-<topic>` for maintenance
- `codex/release-vX.Y.Z` for version and release preparation
- `codex/hotfix-vX.Y.Z` for urgent compatible fixes and their patch release

The `codex/` prefix is this repository's naming convention. Keep unrelated changes
in separate branches. Rebase a personal feature branch onto current `main` when
needed; never rewrite shared `main` or move an already published version tag.
Delete feature branches after their pull requests are merged.

## Commits and pull requests

Use English Conventional Commit subjects: `type(scope): imperative summary`.
Common types are `feat`, `fix`, `docs`, `test`, `refactor`, `build`, `ci`, and `chore`.
Scope is optional. Mark breaking changes with `!` and describe the migration in
the pull request. Keep commits focused and exclude credentials, local agent
reports, caches, generated packages, and installation state.

Use a Conventional Commit subject for the PR title too. Describe the problem,
resulting behavior, validation, and relevant limitations. Prefer **squash merge**
for one coherent change per pull request; preserve individual commits only when
their separation helps future review or reversion.

The `Checks` workflow runs regression and syntax checks on pull requests to main.
These are workflow conventions, not proof that GitHub branch protection has been
enabled. Repository administrators can require the `test` check and PR review in
branch rules; changing those settings is separate from this document.

## Validation

Run from the repository root:

```bash
python3 -m unittest discover -s tests
python3 -m compileall -q bin scripts tests
zsh -o NO_BG_NICE -n setup.sh install.sh uninstall.sh bin/watchsmith bin/codex-watch bin/activitysmith-keychain-setup bin/activitysmith-test
git diff --check
```

Tests use temporary installations and mocked notification/update transports.
Report actual device and hosted CI verification separately. Update both README
languages and affected architecture, upgrade, and troubleshooting documentation
when behavior changes.

## Versions and releases

Use semantic versions (`MAJOR.MINOR.PATCH`) and matching `vX.Y.Z` tags. During
0.x development, use minor releases for substantial features or compatibility
changes and patch releases for compatible fixes. Keep unreleased work marked
with a development suffix in `VERSION`.

Prepare `VERSION` and release documentation on a release branch, merge its PR,
and tag the reviewed commit on `main`. A stable tag triggers the release workflow,
which tests and builds a package from that exact commit before publishing.
Publishing a feature branch is not permission to merge it or create a release.
Do not change published tags or silently replace released assets; publish a new
version for corrections. See [release updates](docs/UPDATES.md).
