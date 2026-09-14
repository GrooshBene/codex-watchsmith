# Release updates

The updater and guided setup are included in v0.2.0 and later. The v0.1.0 release does not contain the updater or its release assets.

## One-time migration

Obtain a version containing the updater, finish active jobs, close affected
Codex clients, and run its `./install.sh --check` followed by
`./install.sh --upgrade --quiesced`. Keep the same `CODEX_HOME`. The installer
adds `watchsmith`, the updater, and the local recovery modules automatically.
Existing credentials and MCP authorization are reused. Restart Codex.

After this one-time migration, Git and a repository checkout are not needed for
updates. Python 3.11+, zsh, network access, and the existing notification setup
are still required. Guided setup and read-only diagnostics are described in [SETUP.md](SETUP.md).

## Commands

```bash
watchsmith version
watchsmith update --check
# Finish jobs and close affected clients before applying:
watchsmith update --quiesced
# Choose a specific newer stable release:
watchsmith update --version v0.2.0 --quiesced
# Undo the latest installation transaction, including installed version metadata:
watchsmith rollback --quiesced
# Recover a specific transaction if necessary:
watchsmith rollback --transaction TRANSACTION_ID --quiesced
```

Replace `v0.2.0` with the newer stable version you want to install. `--check` reads
GitHub release metadata and displays the installed/available versions and a
release-notes link without changing local files. It checks asset availability,
not the package contents. Application downloads and verifies the package before
executing its installer. The command without `--quiesced` does not apply changes;
the flag confirms jobs have stopped, it does not terminate them.

The updater follows its installed directory, so an unrelated `CODEX_HOME` in a
shell cannot redirect it to a different installation. It only uses published
stable releases from `GrooshBene/codex-watchsmith`. It does not pull `main`,
install prereleases, downgrade, or automatically run in the background. Rollback
uses local journals and does not require a network connection or Git. It restores
the latest installation transaction, which may be a manual install rather than
a version update; select a transaction explicitly when needed. Conflict checks
preserve intervening user changes. Existing file-by-file rollback limitations
continue to apply; remote notifications cannot be retracted.

## Package and trust model

Each release supplies `codex-watchsmith-vX.Y.Z.tar.gz` , `SHA256SUMS`, and the standalone `watchsmith-bootstrap.py` setup entry point.
The archive contains a versioned `release.json` with the source commit and file
hashes. The updater verifies the archive checksum, version, complete inventory,
and individual file hashes. Unsafe paths, links, duplicate members, excessive
sizes, incomplete packages, unexpected URLs, and insecure redirects are rejected
before any release installer runs. No arbitrary repository or download URL option
is provided.

Checksums detect corruption and inconsistent assets; they are not publisher
signatures. Trust rests on HTTPS and the official GitHub repository/release
account. Signing is not implemented. Missing assets (including v0.1.0) produce a
manual-upgrade explanation. Network or verification failures leave installed
files unchanged. Failures during installation use the existing recovery journal.

The installed manifest records version, source commit, package SHA-256, and source
kind. Checkout installations are marked `checkout` and have no release commit or
package checksum. Older manifests may report an unknown version. Backups and
journals stay local; treat them as private configuration.

## Publishing

1. Set `VERSION` to the intended stable `X.Y.Z`, update documentation, and commit.
2. Push the matching `vX.Y.Z` tag. The release workflow runs the regression suite
   on macOS, builds committed inputs, and creates a GitHub release with both assets.
3. Review the generated release notes and verify the published assets. An existing
   release is not silently overwritten by the workflow.

For a local packaging check:

```bash
python3 scripts/build-release.py --ref vX.Y.Z --output dist
```

The builder reads the exact Git commit, not uncommitted work. Packages include
runtime/configuration files and user documentation; tests, local reports, agent
state, credentials, and Git history are not packaged. `dist/` is ignored by Git.
Packaging rejects development versions; a stable VERSION must be committed before tagging. Check the GitHub workflow result for each tag; local tests do not certify a hosted CI run.

On macOS, downloads use `/usr/bin/curl` with system certificate verification and explicit per-hop HTTPS/host checks. This avoids relying on an independently installed Python certificate bundle. TLS verification is never disabled.
