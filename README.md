# codex-watchsmith

[한국어 README](README.ko.md)

Mobile progress and completion notifications for long-running Codex work.

`codex-watchsmith` combines:

- **ActivitySmith MCP + global `AGENTS.md`** for semantic, agent-driven Live Activities.
- **Codex `notify` dispatcher** for generic completion Push notifications while preserving any existing notifier such as Computer Use.
- **60-second external watchdog** for long `codex exec` jobs when the agent forgets to notify.

macOS-first.

## Quick start

```bash
git clone https://github.com/<YOUR_GITHUB>/codex-watchsmith.git
cd codex-watchsmith
./install.sh

npm i -g activitysmith-cli@latest
echo 'export PATH="$HOME/.codex/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

activitysmith-keychain-setup
activitysmith-test
```

Then restart Codex.

Configure ActivitySmith MCP separately in Codex. MCP is the rich semantic progress layer; the CLI/API key is used by the external notifier/watchdog.

## What install.sh changes

Files:

```text
~/.codex/
├── AGENTS.md
├── config.toml
├── bin/
│   ├── codex-watch
│   ├── activitysmith_notify.py
│   ├── watchsmith_notify_dispatcher.py
│   ├── activitysmith-keychain-setup
│   └── activitysmith-test
└── watchsmith/
    ├── previous_notify.json
    └── config.toml.backup.*
```

If `config.toml` already has a top-level `notify`, Watchsmith preserves its argv in `previous_notify.json`.

Codex is then configured to call:

```toml
notify = ["python3", "/Users/you/.codex/bin/watchsmith_notify_dispatcher.py"]
```

The dispatcher fan-outs the payload to both:

```text
Codex agent-turn-complete
        │
        ▼
 Watchsmith dispatcher
   ├─ previous notifier (preserved)
   └─ ActivitySmith generic completion Push
```

This allows existing Computer Use notification hooks to coexist.

## Global Codex instructions

The installer appends `config/activitysmith-agents.md` once to `~/.codex/AGENTS.md`.

Default decision policy:

- likely ≥ ~1 minute → proactively use ActivitySmith
- multi-step / multi-tool work → use ActivitySmith
- if a task unexpectedly crosses ~1 minute → promote it
- meaningful progress → Live Activity
- completion / failure / blocker / user input → Push
- never send prompts, credentials, customer data, source code dumps, or confidential content

Edit the policy in `~/.codex/AGENTS.md` after installation if desired.

## 60s watchdog

For one-shot work:

```bash
codex-watch codex exec "run the full test suite and fix failures"
```

Default threshold is 60 seconds.

Test with 10 seconds:

```bash
CODEX_WATCH_THRESHOLD_SECONDS=10 \
codex-watch codex exec "perform a multi-step analysis"
```

If your ActivitySmith CLI supports `activitysmith activity stream`, the fallback is a Live Activity. If not, Watchsmith automatically falls back to a Push notification.

Agent-side ActivitySmith MCP Live Activities are independent and can still work even when the CLI lacks `activity stream`.

## Why both MCP and a watchdog?

`AGENTS.md` is policy, not a timer. During a long blocking tool call, Codex may not regain control at exactly 60 seconds.

```text
Agent/MCP     = meaningful status ("running tests", "rendering audio")
Watchdog      = hard fallback ("this process is still running after 60s")
notify hook   = reliable generic completion signal
```

## Security

- ActivitySmith API key is stored in macOS Keychain (`activitysmith-codex`).
- The completion notifier deliberately ignores prompt and assistant-message fields.
- Existing notifier argv is stored locally under `~/.codex/watchsmith`.
- Do not commit local keys or `.codex` state.

## Verify

```bash
activitysmith-test
grep '^notify' ~/.codex/config.toml
which codex-watch
```

Then complete a small Codex turn and verify the completion Push.

## Limitations

- `codex-watch` is intended for `codex exec` and other one-shot processes.
- Wrapping a permanently open interactive TUI measures process lifetime, not individual turn lifetime.
- Exact 60-second Desktop/Work fallback requires a reliable task-start event surface. For Desktop/Work, ActivitySmith MCP + global instructions remain the primary path.
- ActivitySmith CLI versions differ; Watchsmith feature-detects `activity stream`.

## Troubleshooting

### `unknown command 'stream'`

Not fatal. `activitysmith-test` and `codex-watch` fall back to Push. MCP Live Activities can continue to use `set_live_activity_stream`.

### `nice(5) failed: operation not permitted`

Current scripts disable zsh `BG_NICE`.

### `read-only variable: status`

Fixed: current scripts use `exit_code`, not zsh's special `status` variable.

## Uninstall

```bash
./uninstall.sh
```

The previous notifier is restored when possible. The tagged `AGENTS.md` block and Keychain entry are intentionally left for manual review.

## License

MIT

## Installer safety and local tests

Python 3.11 or newer is required for TOML validation. Installation supports `CODEX_HOME` (default: `~/.codex`). The installed dispatcher finds its state and sibling notifier relative to its own location, including when a GUI process does not export `CODEX_HOME`.

The installer validates the entire TOML document before replacing the root `notify`. Multiline arrays and quoted keys are supported; nested settings remain unchanged. Invalid TOML or non-string notify arguments stop installation without editing the configuration. Backups use unique names, and configuration replacement is atomic. Reinstalling an unchanged dispatcher preserves the saved notifier. A JSON `null` records that no previous notifier existed. Missing saved state stops reinstallation/removal rather than guessing a replacement.

Uninstall restores the saved argument array only if the root notifier is still this installation's dispatcher. A notifier changed by the user is retained. Notify formatting may be normalized; the original text is available in the backup. Global policy updates and full installation rollback are still pending.

Run the isolated regression suite without changing your Codex setup or sending notifications:

```bash
python3 -m unittest discover -s tests -v
```

Tests cover installation/removal, exact argument forwarding to a recording notifier, and generic completion command construction with a mocked CLI. They do not verify the real Computer Use client, Codex event emission, or mobile delivery.
