# Architecture

```text
                        ~/.codex/AGENTS.md
                               │
                               ▼
                       ActivitySmith MCP
                    semantic progress updates
                               │
                               ▼
                             iPhone
                               ▲
                ┌──────────────┴──────────────┐
                │                             │
     notify dispatcher                  codex-watch
 agent-turn-complete Push              60s fallback
                │                             │
      existing notifier                   codex exec
        preserved
```

The agent provides semantic state. The watchdog provides timing fallback. The dispatcher preserves existing integrations and adds completion notification.

## Configuration ownership

`bin/watchsmith_config.py` uses Python 3.11+ `tomllib` to validate the complete config and locate the root notify assignment using parseable prefixes. This avoids interpreting TOML as Python or confusing multiline strings with settings. Only that assignment is replaced, with TOML-compatible JSON string escaping. Unique backups and atomic file replacement protect config writes; the installer now wraps managed executable/config/policy changes in a recovery journal; it is not a single atomic filesystem switch.

`previous_notify.json` contains the original string argv array, or `null` for no notifier. An unchanged dispatcher installation is a no-op for configuration. Uninstall restores only a dispatcher owned by the current installation and fails if its saved state is missing. The dispatcher derives its installation root from its own resolved path, launches the previous argv with the untouched payload appended as one argument without a shell, then independently launches the completion notifier. Both children remain detached.

The isolated tests exercise a recording notifier and mock completion transport. Real Computer Use behavior, Codex-originated events, and device delivery require separate integration verification.

## Optional result summaries

The agent produces a reviewed versioned result record and may use `watchsmith_result.py` to build arguments for the existing ActivitySmith MCP. The helper is local-only; explicit switches include metadata and an optional reviewed HTTPS result link. No transport, credential storage, approval backend, or artifact hosting is added. The completion hook extracts a bounded current-event preview by default. See [RESULTS.md](RESULTS.md) for the contract, consent boundaries, metadata limits, and known duplicate-notification limitation.

Reinstallation backs up and atomically updates only the marked global agent-policy block. Ambiguous markers are rejected before notify configuration is changed; surrounding personal instructions remain intact. These writes now participate in a journaled installer transaction with conflict-aware rollback.

## Completion coordination and migration

watchsmith_delivery.py keeps terminal-event claims in a private local SQLite database scoped to the installed root. The generic notifier waits for pending detailed claims, records CLI service responses, and limits a correlated event to one generic attempt. Exact pre-final turn identity must be supplied by the runtime for MCP-to-hook coordination; it is not inferred from thread ID alone. A remote send and local acknowledgment are not atomic, so crash-after-send duplication remains possible. Wrapped-process progress now uses a separate private run context and shared stream key; see [PROGRESS.md](PROGRESS.md). Run identity is never substituted for terminal thread/turn identity.

watchsmith_install.py validates known runtime hashes, saves original dependencies and per-transaction file images, rejects modified owned files, and restores dependencies before config on removal/rollback. Quiescence is an operator precondition; a lock serializes participating installers. See [UPGRADING.md](UPGRADING.md) for limits and executable commands.

## Computer Use restart compatibility

When the recognized Computer Use callback is configured, the installer keeps it
outside Watchsmith: `Codex → Computer Use → Watchsmith dispatcher`. The dispatcher
forwards to the original inner notifier and sends its own completion notification.
This prevents a restart from adding another Computer Use layer. The supported
shape is `SkyComputerUseClient turn-ended [--previous-notify JSON]`.

For an existing managed installation that Desktop has rewrapped, the installer
reconciles the saved matching envelope without changing the outer config. A
manifest and unchanged saved notifier are required. Unknown or mismatched chains
stop for review. Reinstallation is a no-op once reconciled; removal restores the
original notifier while retaining Computer Use. No extra first-install action is
required. External callback execution is separate from watchdog timing; the earlier
callback timeout is not evidence of a watchdog failure.

## Release updater

`watchsmith update` retrieves and verifies official versioned release assets before invoking the bundled Python installer with `sys.executable`. The updater, bootstrap, and setup wizard retain their running interpreter when starting the next Python stage instead of reselecting `python3` through a shell. Rollback already uses the running interpreter. Version/commit/checksum metadata participates in the same installation journal. Installed installer/configuration modules support offline rollback without a checkout. No additional notification or update server is introduced. See [UPDATES.md](UPDATES.md).

## Guided setup

`watchsmith_setup.py` separates interactive configuration from read-only diagnostics. Source-package setup invokes the existing installer; installed setup completes optional connection/PATH steps. The release builder assembles a standalone bootstrap using the same updater verification functions, then starts setup from a verified archive. See [SETUP.md](SETUP.md).

## Live Activity dismissal

MCP agent policy and wrapper CLI termination both specify final status and `auto_dismiss_minutes=0` in the end content state. Remote completion, Lock Screen dismissal, and retained app history are distinct states; only device observation confirms removal. See [PROGRESS.md](PROGRESS.md).

Shared progress contexts now retain a bounded, explicitly supplied content state and immutable type under the existing file lock. New fallback-first contexts choose elapsed timer; legacy contexts retain progress. MCP claims return the chosen content and reject type rotation by returning the existing type. This does not associate Desktop tasks with wrapper runs. The result argument builder separately supports opt-in Lock Screen previews; the hook queue route below shares the existing completion claim.

## Reviewed completion routing

The notifier extracts request/result sentences directly from the current completion event in memory, with bounded input/output and basic filtering. It does not read session history or invoke another model. Optional reviewed previews require exact thread/turn IDs in the existing private summaries table; legacy marker-only entries are ignored. Both routes share the existing generic-owner delivery claim. No final-response marker is generated or required. Unknown direct-MCP outcomes suppress retries; storage failures and independent senders remain best-effort. Preview extraction changes the default sharing boundary; see RESULTS.md for the environment opt-out and privacy limitations.
