# ACP Run Internals — Known Quirks

## events.jsonl: `event` field, not `state`

When polling for run completion programmatically, each line in `events.jsonl` uses the `event` or `event_type` field to indicate what happened — NOT a `state` field.

```json
{"event": "dispatch_completed", "event_type": "dispatch_completed", ...}
```

Common event values to check for:
- `dispatch_completed` — run finished
- `adapter_completed` — agent adapter finished executing
- `classifier_result` / `classifier_error` — output validation result
- `message_sent`, `dispatch_started` — intermediate states

Do NOT look for `state` field in events. Look for `event` or `event_type`.

## classifier_result.json: Can be NDJSON, not valid JSON

The `artifacts/classifier_result.json` file may contain multiple JSON objects concatenated (NDJSON format), not a single valid JSON document. This happens when the ACP pipeline encounters parse errors writing the classifier result.

When reading it:
```python
# Fragile — crashes on NDJSON:
json.load(open('classifier_result.json'))

# Robust — handles NDJSON:
raw = open('classifier_result.json').read()
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    # Try NDJSON — grab last valid object
    for line in reversed(raw.strip().splitlines()):
        try:
            data = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
```

## run.json: `state` vs `status` inconsistency

Run records can have diverging `state` and `status` fields after a daemon crash mid-dispatch. `state` is the canonical field. `status` may lag behind or be missing entirely.

| Field | Reliability |
|---|---|
| `state` | Canonical — reflects actual run lifecycle |
| `status` | May be stale or missing after crashes |
| `from.model` | Reflects dispatch-time envelope, NOT actual execution model |

To find the actual execution model, check the `adapter_completed` event in `events.jsonl`:
```
ACP_ADAPTER: calling acpx opencode exec (model=opencode/deepseek-v4-flash-free)
```

## Output artifact: Can contain raw acpx NDJSON

For some providers (opencode, codex), the `output_*.md` artifact contains the raw acpx JSON-RPC negotiation stream (session init, model listings, tool config) instead of a clean agent response. The output validator correctly classifies this as `provider_error` or `parse_error`.

This happens because the ACP adapter writes the full acpx NDJSON output to the artifact file. Providers that return clean ACP message formats (claude, pi) produce clean artifacts. Providers that return verbose NDJSON (opencode, codex) produce raw protocol dumps.

## Smoke Matrix

The cross-provider smoke matrix at `$AGENT_OS_HOME/.config/agent-workflows/acp/acp_provider_smoke.py` (symlinked as `acp-provider-smoke`) handles all of these quirks:

- Polls events.jsonl using `event` field
- Falls back to NDJSON parsing for classifier_result.json
- Reports per-provider: run state, validator status, smoke string found
- Saves JSON dump to `~/.local/state/agent-os/acp/smoke/<date>.json`
