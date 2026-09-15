# Message scenarios

Watchsmith prepares 29 state-specific message variants using existing ActivitySmith MCP tools. This is a local argument builder plus managed agent guidance, not an approval server or autonomous job runner. The helper never sends notifications, runs commands, waits for decisions, or registers a completion queue in scenario mode. Installation updates the existing result helper and managed policy; no extra service is needed.

## Catalog

| Scenario | Meaning | Preferred presentation |
|---|---|---|
| analysis | Inspect the task | Elapsed timer |
| planning | Plan the work | Elapsed timer |
| implementation | Implement changes | Segmented progress |
| validation | Validate changes | Segmented progress |
| tests | Run a measured test workload | Progress |
| build | Build artifacts | Elapsed timer |
| download | Download data | Progress |
| upload | Upload data | Progress |
| installation | Install components | Segmented progress |
| deployment | Deploy a release | Segmented progress |
| retrying | Retry an operation | Elapsed timer, orange |
| recovery | Recover from a failure | Segmented progress, orange |
| measurement | Show numeric measurements | Metrics |
| statistics | Show measured totals | Stats |
| blocked | Explain why work stopped | Alert, orange |
| authentication | Request local authentication attention | Alert, orange |
| failure | Explain an error | Alert, red |
| approve_validation | Run validation / stop here | Approval request |
| approve_commit | Commit / stop here | Approval request |
| approve_push | Push / keep locally | Approval request |
| approve_release | Publish / hold | Approval request |
| approve_retry | Retry / stop | Approval request |
| approve_alternative | Use the described alternative / stop | Approval request |
| approve_resume | Resume reviewed work / stop | Approval request |
| completed | Verified completion | Existing completion hook |
| partial | Partial completion | Existing completion hook |
| failed | Failed task | Existing completion hook |
| cancelled | User chose to stop | Existing completion hook |
| expired | Decision deadline expired | Existing completion hook |

Preferred layouts apply when starting a card. For a continuing card, preserve its type, stream key and timer origin. Unknown percentages or step totals default to elapsed time. Explicitly selected layouts require their real measurements; contradictory fields fail locally. Metrics/stats always require measured data. No artificial progress, success status or periodic heartbeat is generated.

## Local preview

```bash
python3 "$HOME/.codex/bin/watchsmith_result.py" --list-scenarios
python3 "$HOME/.codex/bin/watchsmith_result.py" message.json --scenario validation --share-preview
```

Use your configured Codex home if different. `message.json` contains reviewed, shareable text:

```json
{
  "task_name": "Installer validation",
  "summary": "Checking rollback behavior after interrupted installation.",
  "stream_key": "installer-validation",
  "current_step": 2,
  "number_of_steps": 3
}
```

Every scenario requires `task_name` (1–60 characters) and `summary` (1–180 characters), both single-line. Live scenarios also require `stream_key`. Optional `activity_type` preserves an existing layout; pass its matching percentage, steps, metrics or `timer_start_at`. The output contains `route`, the suggested existing MCP `tool`, and its `arguments`. Under a wrapper, use the progress claim helper first and prefer its returned key/type/content to the proposal. Without a wrapper, the agent must preserve the card identity itself.

Terminal scenarios output a preview and status with `route=completion_hook`, without a send tool. Include that reviewed outcome in the final answer for automatic extraction, or use the existing separate exact-ID queue workflow. Scenario mode cannot be combined with queue, metadata or link flags. It does not change automatic completion extraction or guarantee verbatim terminal preview delivery.

## Concrete decisions

```json
{
  "task_name": "Installer fix",
  "summary": "Validation passed. Commit the reviewed staged changes with the shown message.",
  "execution_context": {
    "tool": "shell",
    "command": "git commit -m \"fix: preserve installer interpreter\""
  },
  "scope": {"type": "repository", "value": "codex-watchsmith"}
}
```

Prepare with `--scenario approve_commit --share-preview`. The helper preserves exact execution context rather than executing it. Review the actual staged diff and scope first. For a local shell approval, provide the actual working directory as scope when shareable; otherwise use local confirmation rather than exposing a private path. Never include credentials or confidential content in commands, arguments or scope. `--share-preview` is an explicit sharing intent, not a privacy scanner.

The active agent uses ActivitySmith `request_approval`, retains the returned approval ID and waits on that same request. Only an explicit approval of the unchanged operation permits the corresponding follow-up; rejection, cancellation and expiry do not. Existing user authorizations are not replaced with extra questions. Native Codex permission gates still apply. A timed-out wait is not an expired approval and must not create another question.

Live Activity is the default approval delivery, so the two choices are visible without a long press. Outside the wrapper, end the owned progress card before requesting approval. Inside the wrapper, pause its progress stream before requesting a Live Activity approval, then resume only when continuing work after the decision. The builder no longer forces Push in wrapper environments. Do not mark the wrapper run ended while it is merely waiting. An approval already containing the result does not need a simultaneous completion Push. After a decision and any follow-up work, the existing completion hook reports the final outcome.

MCP Tasks-based approvals are optional only when client support and result retrieval are verified. The agent guidance is not a persistent execution ledger: restart recovery and crash-safe exactly-once follow-up execution remain unimplemented. After a disconnected session, verify remote decision, local target state and whether the action already ran before doing anything else. Three-way decisions require another question; the dedicated approval tool has two action labels.

## Validation boundaries

Local tests cover all scenarios, missing and malformed measurements, exact decision context preservation, wrapper Push selection, terminal routing, and CLI sharing requirements. They do not certify actual mobile rendering of every layout, remote approval response delivery, or follow-up execution across client restarts. Use explicit test operations before enabling a production approval workflow.


## Progress pause and resume around decisions

Use `python3 "$WATCHSMITH_PROGRESS_HELPER" approval-pause` before a wrapper approval. A `send` result supplies a transition token and existing MCP pause tool arguments, including terminal waiting text and immediate dismissal. Invoke that tool once, then record the result using `approval-finish --token TOKEN --outcome accepted` only on explicit success (`failed` for definite failure, `unknown` for ambiguity). Require `recorded=true`; a later `ready` means this local run already recorded a successful pause. `wait`/`skip` must not start a new approval card.

The local gate suppresses both progress claims and watchdog fallback while pausing, paused or resuming. It does not close the run. To continue after a decision, call `approval-resume`, use the returned MCP resume arguments, record the outcome, then follow the usual claim/set/finish flow with the original key/type/timer origin. Rejection/cancellation/expiry that ends work does not need a resume. Clean up the owned stream using the existing end procedure; process exit also attempts key cleanup.

An unknown remote outcome remains fenced: do not infer success, invent a new key or automatically retry. Inspect remote state; if it cannot be reconciled, stop the run and clean up the owned stream. Transition tokens reject stale acknowledgments and closed runs cannot reopen. This is progress-display coordination, not an approval execution ledger or durable restart recovery.

Explicit `delivery=push_notification` or `auto` remains available as a fallback when suitable and includes a long-press hint in the details. Automatic display receipt is unavailable; do not switch surfaces merely because a user has not answered. Confirm cancellation before replacing an existing request. Command approval Push titles may be `Approve command` rather than the question text. Successful service delivery does not certify Lock Screen visibility.
