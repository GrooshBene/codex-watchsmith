# codex-watchsmith

[한국어 README](README.ko.md)

Mobile progress and completion notifications for long-running Codex work.

`codex-watchsmith` combines:

- **ActivitySmith MCP + global `AGENTS.md`** for semantic, agent-driven Live Activities.
- **Codex `notify` dispatcher** for generic completion Push notifications while preserving any existing notifier such as Computer Use.
- **60-second external watchdog** for long `codex exec` jobs when the agent forgets to notify.

macOS-first.

## Before you install

Watchsmith adds notification integration to an existing Codex setup. The installer does not install Codex, Python, Node.js, or ActivitySmith, create an account, or connect MCP. Complete the following preparation before following Quick start.

### 1. Prepare your Mac

- **macOS with zsh:** the scripts use zsh and macOS Keychain.
- **A working Codex installation:** sign in and confirm you can complete a small task. Install Codex CLI as well if you want to use `codex-watch codex exec`; Desktop alone does not provide that command.
- **Python 3.11 or newer:** `python3` must be available in your command path. The installer stops if Python or its TOML parser is unavailable.
- **Node.js and npm:** needed to install and run ActivitySmith CLI using the commands below. See the [ActivitySmith CLI guide](https://activitysmith.com/sdks/cli) for its runtime requirements.
- **The repository files:** the Quick start uses Git. If Git is unavailable, download and extract the repository ZIP, then open a terminal in that folder and start at `./install.sh`.

Check the command-line prerequisites:

```bash
python3 --version   # must be 3.11 or newer
node --version
npm --version
# Required for the CLI watchdog; optional for Desktop-only use:
codex --version
```

If a required command is missing, install that tool before continuing. Watchsmith currently checks Python automatically; it does not perform a complete prerequisite check.

### 2. Prepare ActivitySmith and your receiving device

Follow the [official ActivitySmith quickstart](https://activitysmith.com/quickstart):

1. Create an ActivitySmith account or sign in.
2. Install the ActivitySmith iOS app and pair your receiving device with that account. Allow notifications; enable Live Activities if you intend to use them.
3. Create an API key in the ActivitySmith web app using the same account. After installing Watchsmith, enter it through `activitysmith-keychain-setup`, which stores it in macOS Keychain. Do not paste it into this repository or your Codex configuration.
4. Send a test notification from ActivitySmith Playground and confirm it appears on the device before troubleshooting Watchsmith.

The Mac needs internet access to install the CLI and send notifications. The device must also be able to receive them. Creating an account and API key alone does not complete device setup.

### 3. Connect MCP if you want agent-driven progress

For Codex to report task stages through ActivitySmith, separately follow the [ActivitySmith MCP setup guide](https://activitysmith.com/integrations/mcp-server) for Codex and complete its authorization flow. Confirm the ActivitySmith tools are available in a new Codex session.

MCP authorization and the CLI API key are separate. MCP is needed for agent-driven progress updates; it is not required for the completion notifier or CLI watchdog. Adding the global agent instructions does not connect MCP automatically.

### 4. Choose the installation location

The default is `~/.codex`. If your Codex setup uses another location, set `CODEX_HOME` to that directory before installation and use the same value for reinstall/uninstall. Add that directory's `bin` folder to your command path instead of the default path shown below.

You do not need to remove an existing `notify` setting: the installer saves it and routes events through the dispatcher. Existing Computer Use compatibility is still under verification; its notifier timed out during the latest check, so preservation of its configuration is not proof of successful operation.

The installer's completion message means local files and configuration have been installed. Finish the CLI installation, command-path setup, Keychain registration, connection test, and Codex restart below before treating notification setup as complete.

## Quick start

```bash
git clone https://github.com/GrooshBene/codex-watchsmith.git
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
│   ├── watchsmith_result.py
│   ├── watchsmith_delivery.py
│   ├── activitysmith_notify.py
│   ├── watchsmith_notify_dispatcher.py
│   ├── activitysmith-keychain-setup
│   └── activitysmith-test
└── watchsmith/
    ├── previous_notify.json
    ├── installation.json
    ├── delivery.sqlite3
    └── transactions/
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

The installer installs or updates the marked block from `config/activitysmith-agents.md` in `~/.codex/AGENTS.md`, backing up the prior file and preserving surrounding instructions.

Default decision policy:

- likely ≥ ~1 minute → proactively use ActivitySmith
- multi-step / multi-tool work → use ActivitySmith
- if a task unexpectedly crosses ~1 minute → promote it
- meaningful progress → Live Activity
- completion / failure / blocker / user input → Push
- never send prompts, credentials, customer data, source code dumps, or confidential content

Keep personal preferences outside the marked block in `~/.codex/AGENTS.md`; reinstalling replaces that managed block.

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

## Upgrade and notification coordination

Run `./install.sh --check` to inspect the existing installation without changing it. Finish active Codex/watchdog tasks and close affected clients, then run `./install.sh --upgrade --quiesced`. The same `CODEX_HOME`, Keychain key, and MCP authorization are reused. The installer records a private transaction journal and stops on unknown/modified owned helpers. Restart Codex and verify actual delivery afterward.

Rollback: `./install.sh --rollback latest --quiesced`. Removal: `./uninstall.sh --quiesced`. Original notifier dependencies are restored from the installation baseline; a user-changed notifier is preserved together with its potential runtime dependencies. See [upgrade and recovery details](docs/UPGRADING.md).

Owned completion senders now share a local event store. Exact duplicate generic events are coordinated; an acknowledged detailed MCP result can suppress the generic result **only when both paths have the same trusted thread and turn IDs**. Automatic pre-final turn correlation is not certified for the tested clients. Missing IDs retain best-effort notifications. Watchdog progress behavior is unchanged, and Computer Use callback compatibility remains unresolved.

## Optional detailed task results

With your authorization, the agent can send a reviewed result summary through ActivitySmith MCP metadata: outcome, changes, verification, limitations, and next step. Metadata is stored by ActivitySmith; it is not a place for raw transcripts, source code, or secrets. Generic notifications remain the default.

`watchsmith_result.py` validates a local result and prints arguments for the existing MCP tool. It does not send or upload anything. Use `--share-details` to include reviewed summaries, and optionally `--include-result-link` for an existing, approved HTTPS result page. No separate server is required. See the [result format and workflow](docs/RESULTS.md) and [example](config/result-example.json).

Metadata storage was verified through MCP history, and the user confirmed detail fields and line breaks in the iOS app. Result-link access has not been verified. The generic completion hook may still send a separate Push; this feature does not yet deduplicate across integrations.

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
./uninstall.sh --quiesced
```

The manifest restores original notifier dependencies before its configuration. The tagged `AGENTS.md` block and Keychain entry are intentionally left for manual review. If the user replaced notify, runtime files are retained for dependency safety.

## License

MIT

## Installer safety and local tests

Python 3.11 or newer is required for TOML validation. Installation supports `CODEX_HOME` (default: `~/.codex`). The installed dispatcher finds its state and sibling notifier relative to its own location, including when a GUI process does not export `CODEX_HOME`.

The installer validates the entire TOML document before replacing the root `notify`. Multiline arrays and quoted keys are supported; nested settings remain unchanged. Invalid TOML or non-string notify arguments stop installation without editing the configuration. Private transaction journals retain original files; individual file replacements are atomic. Reinstalling an unchanged dispatcher preserves the saved notifier. A JSON `null` records that no previous notifier existed. Missing saved state stops reinstallation/removal rather than guessing a replacement.

Uninstall restores the saved argument array only if the root notifier is still this installation's dispatcher. A notifier changed by the user is retained. Notify formatting may be normalized; the original text is available in the backup. The managed policy is updated on reinstall; journaled installation recovery is now available; see the upgrade guide.

Run the isolated regression suite without changing your Codex setup or sending notifications:

```bash
python3 -m unittest discover -s tests -v
```

Tests cover installation/removal, exact argument forwarding to a recording notifier, and generic completion command construction with a mocked CLI. They do not verify the real Computer Use client, Codex event emission, or mobile delivery.
