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

The agent produces a reviewed versioned result record and may use `watchsmith_result.py` to build arguments for the existing ActivitySmith MCP. The helper is local-only; explicit switches include metadata and an optional reviewed HTTPS result link. No transport, credential storage, approval backend, or artifact hosting is added. The completion hook remains generic. See [RESULTS.md](RESULTS.md) for the contract, consent boundaries, metadata limits, and known duplicate-notification limitation.

Reinstallation backs up and atomically updates only the marked global agent-policy block. Ambiguous markers are rejected before notify configuration is changed; surrounding personal instructions remain intact. These writes now participate in a journaled installer transaction with conflict-aware rollback.

## Completion coordination and migration

watchsmith_delivery.py keeps terminal-event claims in a private local SQLite database scoped to the installed root. The generic notifier waits for pending detailed claims, records CLI service responses, and limits a correlated event to one generic attempt. Exact pre-final turn identity must be supplied by the runtime for MCP-to-hook coordination; it is not inferred from thread ID alone. A remote send and local acknowledgment are not atomic, so crash-after-send duplication remains possible. Watchdog progress is unchanged.

watchsmith_install.py validates known runtime hashes, saves original dependencies and per-transaction file images, rejects modified owned files, and restores dependencies before config on removal/rollback. Quiescence is an operator precondition; a lock serializes participating installers. See [UPGRADING.md](UPGRADING.md) for limits and executable commands.
