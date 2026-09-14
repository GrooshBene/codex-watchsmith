# Troubleshooting

## `unknown command 'stream'`
Your ActivitySmith CLI lacks the Live Activity CLI subcommand. Watchsmith automatically falls back to Push. MCP Live Activity remains independent.

## Existing notifier
```bash
cat ~/.codex/watchsmith/previous_notify.json
grep '^notify' ~/.codex/config.toml
```

## API key
```bash
security find-generic-password -a "$USER" -s activitysmith-codex -w >/dev/null && echo OK
```

## Direct test
```bash
activitysmith-test
```

## Installation stops before changing config

Use Python 3.11+ (`python3 --version`). Invalid TOML and a root `notify` that is not an array of strings are rejected. Correct the reported configuration problem and rerun installation. Multiline notify arrays are supported.

If `previous_notify.json` is missing while the dispatcher is configured, reinstall/uninstall deliberately stops. Review the legacy `config.toml.backup.*` files or new transaction journals in `${CODEX_HOME:-$HOME/.codex}/watchsmith` and recover the original notify setting before retrying. Do not invent a previous notifier when Computer Use may depend on it. Backups can contain private settings; do not post their contents publicly.

For a custom `CODEX_HOME`, use that same value when installing and removing. The dispatcher itself locates state next to its installation and does not require the variable at runtime. Reinstalling preserves saved argv; uninstall preserves a notifier changed by the user.

Run `python3 -m unittest discover -s tests -v` from the repository for offline regression checks. A passing test suite does not establish mobile Push delivery or real Computer Use behavior.

## Detailed result metadata

`watchsmith_result.py` only prints JSON: an agent must pass that object to the existing ActivitySmith MCP send tool. Without `--share-details`, output intentionally omits details. Check ActivitySmith history for metadata; a successful send is not proof of mobile display. A local Mac path is not a mobile result URL. Never work around missing metadata support by putting private details in the notification body or payload.

Oversized fields or metadata fail without truncation: shorten the reviewed summary. Unknown fields are rejected; use [the documented contract](RESULTS.md). A second completion notification may come from the existing hook/notifier; cross-process deduplication is not implemented.

If reinstall reports ambiguous policy markers, inspect the BEGIN/END Watchsmith block in the global AGENTS.md. Restore one correctly ordered pair before retrying. Personal instructions should be outside that managed block. New installations save original policy bytes in watchsmith/transactions/*/journal.json; older policy backups may exist under watchsmith/AGENTS.md.backup.*.

## Upgrade stops or duplicate completion persists

Use `./install.sh --check` and [UPGRADING.md](UPGRADING.md). Unknown runtime hashes require review; do not add a hash merely to bypass the check. An interrupted transaction requires `--rollback ID --quiesced`. Stop affected clients before setting --quiesced.

Deduplication needs exact thread/turn IDs and cooperating senders sharing the same installed root. Check whether the detail sender recorded its successful claim before the hook ran. If no trusted turn ID is available, keep generic fallback rather than guessing. An unknown delivery outcome may have reached the remote service; do not blindly replay it. Existing external notifiers can still send independently.
