# Guided setup and diagnostics

Guided setup is available in v0.2.0 and later. v0.1.0 does not contain the wizard or bootstrap asset.

## Start from a downloaded package or checkout

```bash
./setup.sh
```

Python 3.11+ and macOS/zsh are still required. The wizard detects ActivitySmith CLI
and offers to install it through npm if npm is available. If Python or npm is
missing, install the prerequisite and rerun; the wizard does not install a system
package manager or run sudo. A working Codex Desktop installation can be used
without Codex CLI; the CLI is needed for wrapped command execution.

The wizard checks existing installation state, asks before applying changes,
reuses the journaled installer, and offers Keychain key entry only when an entry
is missing. Existing entries are detected by presence; a test notification is
needed to check whether the credential works. No API key is printed, copied into
shell startup files, or included in diagnostic JSON. Existing shell files are
privately backed up before an optional PATH addition. Symlinked shell files are
left for manual configuration.

The wizard guides account/device pairing and separate MCP authorization with
links. These steps remain in ActivitySmith and Codex; a config entry does not
prove MCP authorization. A test notification is sent only on request, and phone
display is confirmed separately from service acceptance. No Live Activity is
started just to test installation.

## Return later or diagnose

```bash
watchsmith setup
watchsmith doctor
watchsmith doctor --json
```

Installed setup completes connection/PATH steps; it does not reinstall files from
an unavailable checkout. Use the updater or a release package to repair runtime
files. Rerunning re-inspects completed steps instead of retaining API keys or
answers in a wizard session file. Finish optional steps later if necessary.

Doctor performs local, read-only checks: prerequisites, Keychain entry presence,
recorded installed-file hashes, saved completion-hook connection, policy markers,
command resolution, and possible MCP config presence. It does not send test
notifications, download releases, mutate state, prove device delivery, or certify
authorization. Keychain access can involve a system permission prompt. Output
contains statuses and guidance, never config contents or key values. Exit 1 means
an error/warning needs attention; MCP authorization remains an informational check.
Restart Codex and open a new terminal after setup so persisted settings are loaded.

Interactive setup requires a terminal and cannot be piped unattended. Existing
`install.sh` and updater flags remain available for explicit scripted installation.
The wizard's consent to install includes confirmation that affected jobs have
finished; it does not terminate user processes.

## One-command entry point

The release builder creates a standalone `watchsmith-bootstrap.py` asset from the
same committed updater verification code and bootstrap entry point. For v0.2.0 and later, macOS users with Python 3.11+ can run:

```bash
( installer_file=$(mktemp) && trap 'rm -f "$installer_file"' EXIT && curl --proto '=https' --tlsv1.2 -fsSL https://github.com/GrooshBene/codex-watchsmith/releases/latest/download/watchsmith-bootstrap.py -o "$installer_file" && python3 "$installer_file" )
```

The subshell preserves interactive stdin, cleans up its temporary file, and does
not change the user's shell. The bootstrap resolves an official stable release,
validates its package/checksum/inventory, then launches setup from that verified
package. Git and manual extraction are unnecessary. No unverified package
installer is executed. The initial bootstrap script itself is trusted via HTTPS
and the official release account; its package checksums are not publisher
signatures. Missing assets, network errors, or verification failures stop before
setup. A download-and-inspect-first workflow is also supported by saving the
bootstrap file and running it manually.

Hosted bootstrap delivery should be verified for each release; actual user authorization prompts depend on the local environment. Local tests verify generated bootstrap behavior with mocked
transport and temporary installations; they do not certify a live release.
