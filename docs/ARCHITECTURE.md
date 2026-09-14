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

`bin/watchsmith_config.py` uses Python 3.11+ `tomllib` to validate the complete config and locate the root notify assignment using parseable prefixes. This avoids interpreting TOML as Python or confusing multiline strings with settings. Only that assignment is replaced, with TOML-compatible JSON string escaping. Unique backups and atomic file replacement protect config writes; this is not yet a transaction covering copied executables and policy installation.

`previous_notify.json` contains the original string argv array, or `null` for no notifier. An unchanged dispatcher installation is a no-op for configuration. Uninstall restores only a dispatcher owned by the current installation and fails if its saved state is missing. The dispatcher derives its installation root from its own resolved path, launches the previous argv with the untouched payload appended as one argument without a shell, then independently launches the completion notifier. Both children remain detached.

The isolated tests exercise a recording notifier and mock completion transport. Real Computer Use behavior, Codex-originated events, and device delivery require separate integration verification.
