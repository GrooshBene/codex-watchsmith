# Shared progress for wrapped commands

`codex-watch <command> ...` creates a private temporary run context and passes
`WATCHSMITH_PROGRESS_CONTEXT` and `WATCHSMITH_PROGRESS_HELPER` to the child.
The updated managed agent policy uses this context to coordinate the existing
ActivitySmith MCP with the CLI watchdog. No additional MCP server is required.
The context contains an opaque stream key and delivery state, never prompts,
responses, credentials, or project paths intended for remote delivery.

## Lifecycle

1. Before a meaningful MCP progress update, the agent invokes
   `python3 "$WATCHSMITH_PROGRESS_HELPER" claim`.
2. On `send`, it calls the existing `set_live_activity_stream` using the returned
   `stream_key`, `content_state.type=progress`, and default target channels.
   On `wait` or `skip`, it does not start a second activity.
3. Immediately after the response, it invokes
   `python3 "$WATCHSMITH_PROGRESS_HELPER" finish --token TOKEN --outcome accepted`.
   Use `accepted` only for an explicit success, `failed` for a known failure,
   and `unknown` for an uncertain result. The claim expires after 90 seconds;
   obtain it immediately before sending. A stale acknowledgment is rejected.
4. The watchdog waits while a claim is pending. Accepted semantic progress
   suppresses fallback for the rest of this process. Failed or expired claims
   permit fallback at/after the configured threshold. Fallback runs at most once.
   If fallback started first, the next MCP update uses its same stream key/type.
5. The agent ends the stream through MCP at task completion and runs
   `python3 "$WATCHSMITH_PROGRESS_HELPER" ended` only after explicit success.
   Otherwise the wrapper attempts to end the shared stream once when the command
   exits. A command exit is reported as execution ended, not task success.

Local file locking serializes claims and watchdog sends. No remote polling or
periodic Live Activity updates are added. The original command's exit code is
preserved; SIGINT/SIGTERM are forwarded to the direct child. Existing completion
hooks and their exact thread/turn delivery claims remain separate and unchanged.

## Boundaries and failure behavior

- This is **one wrapped process**, intended for `codex exec` and similar one-shot
  commands. It is not a turn identity and must not suppress a completion hook.
- Desktop tasks outside the wrapper, interactive multi-turn sessions, and clients
  that strip the context environment or cannot write it do not gain this bridge.
  An agent that ignores the managed policy still operates independently.
- The CLI must support stream/end-stream to manage the shared Live Activity.
  When stream is unavailable and no MCP stream may exist, fallback is one generic
  Push. If MCP may already have started, an extra Push is avoided. With an old CLI,
  the agent must end its Live Activity via MCP.
- CLI calls have bounded waits. An uncertain stream send is not retried as a
  separate Push. Remote acceptance is not proof of device display.
- A remote MCP request and local acknowledgment are not atomic. The shared key
  avoids deliberately creating a second stream, but an in-flight request finishing
  after process cleanup can still leave an activity. Forced process termination
  can bypass cleanup. Exactly-once delivery is not guaranteed.
- Corrupt/unavailable local progress state does not terminate the user's command;
  the wrapper reports the monitoring/cleanup failure. Completion hooks still run
  independently. Abandoned temporary contexts after a hard kill may require cleanup.

## Applying the change

Run `./install.sh --check`, then finish active jobs and close affected clients.
Run `./install.sh --upgrade --quiesced` and restart Codex. This installs the progress
helper, wrapper and managed policy together. Keychain and MCP authorization are
reused. See [UPGRADING.md](UPGRADING.md) for rollback and compatibility constraints.

Automated tests cover process environment propagation with a simulated agent,
concurrent claims, both start orders, acknowledgment outcomes, expiry, cleanup,
unsupported CLI fallback, and command exit preservation. Real Codex tool-shell
propagation and mobile handover require separate integration verification.

## Dismissal after completion

Both the managed MCP policy (including Desktop outside the wrapper) and wrapper CLI end payload request `content_state.auto_dismiss_minutes=0`. MCP endings include truthful final status and retain the stream key/type. The wrapper reports process exit, not independently verified task success; nonzero exits do not show 100%. This requests immediate Lock Screen removal rather than leaving a completed card beside the next task. It does not delete app history or guarantee APNs/device delivery. Do not recreate or repeatedly end a completed stream to force removal.
