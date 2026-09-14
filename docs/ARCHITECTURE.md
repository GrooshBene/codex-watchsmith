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
