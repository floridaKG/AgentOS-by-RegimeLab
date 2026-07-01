# Agent Voice

## Purpose

Agent Voice is an append-only insight buffer that allows any Agent OS agent to emit proactive observations about how Agent OS should evolve. It provides a shared, stable schema for capturing friction, improvement ideas, and risks with evidence and self-declared confidence levels. The system implements the AV-1 insight event contract, with AV-2 (passive) and AV-3 (active) delivery surfaces reading from the same buffer.

## How it works

Agent Voice stores insights as append-only JSONL at `~/.local/state/agent-os/agent-voice/insights.jsonl`. Each insight is a single JSON line with a stable schema:

- **id** — unique identifier with timestamp and random suffix
- **kind** — one of `friction`, `improvement`, `risk`, `pattern`, `question`
- **summary** — one-line description
- **evidence** — supporting observations or data
- **confidence** — `low`, `medium`, or `high` (defaults to `low`)
- **source_ref** — reference to the source session or file
- **emitting_agent** — the agent that created the insight

### CLI usage

The `agent-voice` CLI wraps `scripts/agent_voice.py` and supports:

| Command | Description |
|---------|-------------|
| `agent-voice emit --kind friction --summary "..." --evidence "..."` | Emit a new insight |
| `agent-voice list [--kind friction] [--limit 10]` | List insights with optional filtering |
| `agent-voice query --kind improvement --status open` | Query insights by kind and status |
| `agent-voice show <id>` | Show a specific insight with full details |

### Storage guarantees

- **Append-only** — insights are never deleted or modified in place
- **fcntl flock** — parallel agents cannot interleave partial lines
- **Feedback folding** — feedback entries are folded into their target insight for a single per-insight view while preserving the audit trail
- **No daemon** — pure local file write, usable by sandboxed agents

### Kinds of insights

| Kind | Description | Example |
|------|-------------|---------|
| `friction` | Something that slowed down or frustrated the workflow | "Git status check on large repos is slow" |
| `improvement` | An idea for making the system better | "Add pagination to memory-recall output" |
| `risk` | A potential problem or concern | "Pinecone dependency is a single point of failure" |
| `pattern` | Something that worked well and should be repeated | "Parallel recall grep across tiers is fast" |
| `question` | An open question about system behavior | "Should lessons be auto-promoted after N days?" |

## Integration points

Agents emit insights via the `agent-voice` CLI or by calling `scripts/agent_voice.py` directly. Insights are stored independently of the memory system and are not auto-promoted to long-term memory — surfacing is an explicit action. The AV-2 surface reads from the same buffer for passive recall, and AV-3 provides active delivery of high-confidence insights.

## Key source files

| File | Purpose |
|------|---------|
| `bin/agent-voice` | CLI entry point (shell wrapper delegating to `scripts/agent_voice.py`) |
| `scripts/agent_voice.py` | Python implementation with emit, list, query, show commands and JSONL storage |
| `skills/shared/lesson/SKILL.md` | Lesson skill; agent voice friction/improvement/risk insights complement lesson capture |
