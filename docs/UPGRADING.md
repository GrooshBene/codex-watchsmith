# Upgrade, deduplication, and recovery

This release adds local completion-event coordination and a journaled installer. It reuses ActivitySmith MCP/CLI, existing credentials, and the original notifier argv. It does not add a server, replace remote approval handling, or change watchdog timing.

## Upgrade an existing computer

Download/extract the new repository version or update your checkout. Use the same `CODEX_HOME` as the existing installation; the default remains `~/.codex`.

```bash
# Read-only: validates runtime syntax and reports files that would change.
./install.sh --check
```

An unknown or modified runtime file, malformed policy, saved dispatcher cycle, or missing saved notifier stops the operation. The known-hash catalog identifies inspected historical runtime files; a matching filename alone is insufficient. Other user-defined notifiers are preserved as argv, but Watchsmith cannot deduplicate arbitrary notifications they send. The Computer Use flag syntax has been verified against the installed client's help, but its valid completion callback still timed out in the integration test.

Finish active Codex/watchdog work and close the affected Codex clients before applying changes. `--quiesced` is the operator's confirmation of this condition, not an automatic process detector.

```bash
./install.sh --upgrade --quiesced
```

The installer prints a transaction ID and stores a private recovery journal under `${CODEX_HOME:-$HOME/.codex}/watchsmith/transactions/`. It snapshots managed file contents, permissions, config, policy, and saved argv. Known owned helpers are updated; the existing Computer Use argv is retained exactly. The current managed block or the recognized legacy `activitysmith autonomous workflow` block is replaced, leaving outside instructions intact. Mixed or malformed marker sets stop the migration.

Keychain credentials, MCP authorization, and detailed-sharing preferences are not reset. You do not need to register the API key again. For a fresh installation, complete the README's CLI, PATH, Keychain, MCP, and device setup steps.

Restart Codex. Test a generic completion, then a reviewed detailed-result flow on a separate turn. The installer reports local validation only; it cannot certify remote delivery or device display. The real Computer Use completion timeout remains a compatibility limitation, so that installation class is not yet certified.

## Recover or roll back

```bash
# Stop affected clients first. Use the printed ID to target an exact transaction.
./install.sh --rollback TRANSACTION_ID --quiesced
# Or target the most recent transaction:
./install.sh --rollback latest --quiesced
```

Individual file writes are atomic; the multi-file operation uses a recovery journal, not a single atomic filesystem switch. An ordinary apply error triggers restoration. A crash leaves a pending transaction that blocks further installs until rollback is performed. Conflicting edits made since the transaction stop automatic restoration rather than being overwritten. Keep journals local: their snapshots may include private configuration.

Repeated installation without changes is a no-op. Repeated rollback of the same unchanged state is safe. A rollback cannot retract already delivered notifications.

## Remove while preserving original hooks

```bash
./uninstall.sh --check
./uninstall.sh --quiesced
```

A manifest is required to remove a managed installation safely. Original helper files and permissions are restored before the original notify setting. For a pre-manifest dispatcher installation, the earliest available baseline may already contain Watchsmith helpers: those baseline files are retained rather than guessed away. Personal policy and credentials remain for manual review.

If the user changed the root notifier after installation, removal leaves both that notifier and runtime files intact because it may depend on them. If owned runtime or saved argv were modified, removal stops for review. Unknown original files are never deleted just because their names match a helper.

## What completion coordination covers

Watchsmith-controlled generic senders share `watchsmith/delivery.sqlite3` under their resolved installation root. The local key is a hash of the exact thread ID, turn ID, and terminal-event role. Raw prompts, responses, and credentials are not stored. Records expire after seven days.

- Concurrent/repeated generic senders for one event receive one send claim.
- A successfully recorded detailed result suppresses a later generic completion for that exact event.
- A live detailed claim makes the detached generic worker wait for its outcome or lease expiry. The default detail lease is 60 seconds, configurable at claim time from 1 to 120 seconds. The generic worker waits at most 125 seconds; its own send has a 30-second timeout.
- A failed/expired detailed claim permits one generic fallback. A generic attempt, including an ambiguous timeout, is not automatically repeated within retention.
- Different turns are independent. Approval requests and progress notifications do not participate in terminal-event deduplication.
- Without exact event IDs, or when local state is unavailable, generic completion remains best effort and is not deduplicated.

A CLI spawn or process exit alone is not recorded as accepted delivery. The current adapter recognizes the inspected CLI's `Success: true` response with exit code 0; other responses are classified as unknown. Unknown delivery can still mean the remote service accepted the request.

## Cooperative MCP result protocol

Use this only when the runtime explicitly provides the **same exact thread and turn IDs** that its completion event will contain. In the tested Desktop tool environment, thread/session variables existed but a turn ID did not. No pre-final automatic CLI/Desktop correlation is certified. Do not select a recent log entry, hash a prompt, or substitute the thread ID for the turn ID. Uncorrelated detailed MCP sends may still coexist with a generic completion.

From an installed command path, using runtime-supplied values:

```bash
watchsmith_delivery.py claim --thread-id "$THREAD_ID" --turn-id "$TURN_ID"
```

Only `action: send` authorizes this protocol's next send. Save its token locally. Add the returned opaque `correlation_tag` to the existing MCP send's `tags`; do not send raw Codex IDs. On `wait` or `skip`, retain the detailed result locally and do not send another terminal Push.

After the existing MCP returns an explicit success response:

```bash
watchsmith_delivery.py finish --thread-id "$THREAD_ID" --turn-id "$TURN_ID" \
  --token "$CLAIM_TOKEN" --outcome accepted
```

Record `failed` only for a known failure before acceptance, or `unknown` when the result is ambiguous. A stale token cannot overwrite a newer claim. These commands coordinate a send; they are not user authorization for sharing details or executing follow-up work.

No automatic cross-service history reconciliation or remote idempotency is implemented. If MCP accepts a send and the agent crashes before recording success, a later generic fallback may duplicate it. The opaque tag supports manual verification using ActivitySmith's existing history tools; do not claim exactly-once delivery. If generic completion wins first, retain the later detail locally rather than posting another terminal notification.

## Watchdog scope

`codex-watch` measures wrapped process lifetime and shares a private run context with the managed MCP policy. Registered MCP success suppresses fallback, and both paths use one stream key. It observes local acknowledgment, not device display. This applies to new wrapped one-shot processes, not arbitrary Desktop tasks or per-turn interactive sessions.

The upgrade also installs `watchsmith_progress.py` and refreshes the wrapper progress policy. Launch a new wrapped command after restarting; already-running processes do not acquire the context. See [PROGRESS.md](PROGRESS.md).

## Computer Use restart compatibility

When the recognized Computer Use callback is configured, the installer keeps it
outside Watchsmith: `Codex → Computer Use → Watchsmith dispatcher`. The dispatcher
forwards to the original inner notifier and sends its own generic notification.
This prevents a restart from adding another Computer Use layer. The supported
shape is `SkyComputerUseClient turn-ended [--previous-notify JSON]`.

For an existing managed installation that Desktop has rewrapped, the installer
reconciles the saved matching envelope without changing the outer config. A
manifest and unchanged saved notifier are required. Unknown or mismatched chains
stop for review. Reinstallation is a no-op once reconciled; removal restores the
original notifier while retaining Computer Use. No extra first-install action is
required. External callback execution is separate from watchdog timing; the earlier
callback timeout is not evidence of a watchdog failure.
