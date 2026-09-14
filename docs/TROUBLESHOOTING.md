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
