#!/usr/bin/env python3
"""ACP Common — shared utilities for Agent Communication Protocol.

Paths, JSON/YAML loading, atomic write with .tmp+rename, lock directory helpers,
custom base62 message_id generator, run state management, role resolution,
and budget checking.

OSS path contract:
  AGENT_OS_HOME  — install root (default: $HOME/agent-os)
  AGENT_OS_ACP_ROOT — ACP state root
    default: $AGENT_OS_HOME/.local/state/agent-os/acp
"""

from __future__ import annotations

import json
import os
import time
import uuid
import tomllib
import fcntl
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants / paths
# ---------------------------------------------------------------------------

_HOME = Path(os.environ.get("HOME", os.path.expanduser("~"))).expanduser()
AGENT_OS_HOME = Path(
    os.environ.get("AGENT_OS_HOME", str(_HOME / "agent-os"))
).expanduser()

CANONICAL_ACP_ROOT = AGENT_OS_HOME / ".local" / "state" / "agent-os" / "acp"
ACP_ROOT = Path(
    os.environ.get("AGENT_OS_ACP_ROOT", str(CANONICAL_ACP_ROOT))
).expanduser()

# Inbox directories
INBOXES = ACP_ROOT / "inboxes"
INBOX_ORCHESTRATOR = INBOXES / "orchestrator"
INBOX_ROUTER = INBOXES / "router"
INBOX_WORKSPACES = INBOXES / "workspaces"
INBOX_AGENTS = INBOXES / "agents"

# Outbox (parent for dynamic agent_id subdirs)
OUTBOXES = ACP_ROOT / "outboxes"

# Run state
RUNS = ACP_ROOT / "runs"

# Multi-agent bridge directories
SESSIONS_DIR = ACP_ROOT / "sessions"
PROJECTS_DIR = ACP_ROOT / "projects"

# Error handling
DEAD_LETTER = ACP_ROOT / "dead-letter"
ARCHIVE = ACP_ROOT / "archive"
TMP_DIR = ACP_ROOT / ".tmp"

# Workflow paths (under install root)
WORKFLOWS_DIR = AGENT_OS_HOME / ".config" / "agent-workflows"
ROLES_TOML = WORKFLOWS_DIR / "roles.toml"
ACP_BUDGET_TOML = WORKFLOWS_DIR / "acp" / "budget.toml"
RUN_AGENT_SH = WORKFLOWS_DIR / "run-agent.sh"

# Registry (agents.yaml lives at install root)
REGISTRY_DIR = AGENT_OS_HOME / "registry"
AGENTS_YAML = REGISTRY_DIR / "agents.yaml"

# Base62 alphabet (0-9, A-Z, a-z)
BASE62_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

# Valid intents
VALID_INTENTS = {"ASSIGN", "ACK", "STATUS", "RESULT", "ERROR", "HELP", "CANCEL", "HEARTBEAT"}

# Valid priorities (sorted high->low for poll ordering)
PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}
VALID_PRIORITIES = set(PRIORITY_ORDER.keys())

# Valid run states
VALID_RUN_STATES = {
    "queued",
    "claimed",
    "running",
    "blocked",
    "awaiting_input",
    "resume_requested",
    "cancel_requested",
    "succeeded",
    "failed",
    "cancelled",
    "dead_lettered",
    # Backward compatibility with earlier ACP drafts.
    "awaiting_help",
    "expired",
    # OSS simplified state machine extras
    "review",
    "resume",
}

TERMINAL_RUN_STATES = {"succeeded", "failed", "cancelled", "dead_lettered", "blocked"}

# Valid git policies. Packet contract forbids write/branch verbs; no "full".
VALID_GIT_POLICIES = {"read-only", "single-file-edit"}

# Valid secrets policies
VALID_SECRETS_POLICIES = {"none", "ops"}

# Valid cost classes
VALID_COST_CLASSES = {"free", "paid", "research"}

# Valid workflow patterns
VALID_WORKFLOW_PATTERNS = {"swarm", "council", "escalate", "orchestrate"}

# Workspace name normalization: variant names -> canonical scope.
# Keep only generic aliases (no private workspace names).
WORKSPACE_ALIASES = {
    "scratch": "home",
}


def normalize_workspace(workspace: str) -> str:
    """Normalize variant workspace names to their canonical scope.

    'scratch' -> 'home'
    canonical names pass through unchanged.

    Must be called at every entry point (acp-task, acp_send, acp_dispatch, etc.)
    before the workspace value is used for inbox routing or memory scope lookup.
    """
    if not workspace:
        return "home"
    return WORKSPACE_ALIASES.get(workspace, workspace)


# Forbidden git commands (case-insensitive check)
FORBIDDEN_GIT_COMMANDS = [
    "git add", "git commit", "git push", "git checkout",
    "git reset", "git stash", "git branch", "git switch", "git clean", "git worktree"
]

# Generic workspaces only (home/work/docs/scratch). No private project names.
GENERIC_WORKSPACES = ("home", "work", "docs", "scratch")

# All state directories to create on setup
STATE_DIRS = [
    INBOX_ORCHESTRATOR,
    INBOX_ROUTER,
    INBOX_WORKSPACES / "home",
    INBOX_WORKSPACES / "work",
    INBOX_WORKSPACES / "docs",
    INBOX_WORKSPACES / "scratch",
    INBOX_AGENTS,
    OUTBOXES,
    RUNS,
    SESSIONS_DIR,
    PROJECTS_DIR,
    DEAD_LETTER,
    ARCHIVE,
    TMP_DIR,
]

# Workspace + Intent -> Role mapping (generic only)
WORKSPACE_INTENT_ROLE = {
    ("home", "DOCS"): "architect",
    ("home", "SPEC"): "architect",
    ("home", "BUG"): "executor",
    ("home", "IMPLEMENT"): "executor",
    ("work", "BUG"): "executor",
    ("work", "IMPLEMENT"): "executor",
    ("work", "REVIEW"): "code_reviewer",
    ("docs", "DOCS"): "architect",
    ("docs", "SPEC"): "architect",
    ("docs", "RESEARCH"): "architect",
}


# ---------------------------------------------------------------------------
# Base62
# ---------------------------------------------------------------------------

def base62_encode(num: int, length: int = 6) -> str:
    """Encode an integer into a base62 string of exactly `length` chars."""
    chars = []
    for _ in range(length):
        chars.append(BASE62_ALPHABET[num % 62])
        num //= 62
    return ''.join(reversed(chars))


def generate_message_id() -> str:
    """Generate a unique message ID.

    Format: msg_<YYYYMMDDTHHMMSSZ>_<6char-base62>
    """
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    # Combine timestamp millis with uuid for uniqueness
    rand_val = (int(time.time() * 1000) & 0xFFFFFFFF) ^ (uuid.uuid4().int & 0xFFFFFFFF)
    suffix = base62_encode(rand_val, 6)
    return f"msg_{ts}_{suffix}"


def generate_run_id(workspace: str = "home", slug: str = "acp") -> str:
    """Generate a collision-resistant run ID.

    Format: <YYYYMMDD>-<HHMMSS>-<workspace>-<slug>-<4char-base62>

    The 4-char random base62 suffix provides ~14M unique values per second,
    making same-second collisions astronomically unlikely while preserving
    a recognizable timestamp/workspace/slug prefix.
    """
    now = datetime.now(timezone.utc)
    rand_suffix = base62_encode(uuid.uuid4().int, 4)
    workspace = normalize_workspace(workspace) or "home"
    # Keep workspace segment path-safe
    workspace = "".join(c if c.isalnum() or c in "-_" else "-" for c in workspace)
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in (slug or "acp"))
    return now.strftime(f"%Y%m%d-%H%M%S-{workspace}-{slug}-{rand_suffix}")


# ---------------------------------------------------------------------------
# State directory management
# ---------------------------------------------------------------------------

def ensure_state_dirs():
    """Create all ACP state directories. Idempotent."""
    for d in STATE_DIRS:
        d.mkdir(parents=True, exist_ok=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    """Read and parse a UTF-8 JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: Path) -> dict:
    """Read and parse a YAML file. Requires PyYAML (optional dep)."""
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required to load YAML files. Install with: pip install pyyaml"
        ) from exc
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_message(path: Path) -> dict:
    """Load a message from JSON or YAML."""
    if str(path).endswith((".yaml", ".yml")):
        return load_yaml(path)
    return load_json(path)


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

def atomic_write(directory: Path, filename: str, data: dict) -> Path:
    """Atomically write a JSON file to `directory/filename`.

    Writes to .tmp first, then renames (atomic on same filesystem).
    Returns the final path.
    """
    target = directory / filename
    tmp_path = TMP_DIR / f"{filename}.{uuid.uuid4().hex}.tmp"

    # Ensure .tmp dir exists
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    directory.mkdir(parents=True, exist_ok=True)

    # Write to tmp
    content = json.dumps(data, indent=2, ensure_ascii=False)
    tmp_path.write_text(content, encoding="utf-8")
    with tmp_path.open() as f:
        os.fsync(f.fileno())

    # Atomic rename
    os.replace(tmp_path, target)
    return target


# ---------------------------------------------------------------------------
# Presence heartbeat
# ---------------------------------------------------------------------------


def write_presence(agent_id: str, role: str, state: str, activity: str = ""):
    """Write a presence heartbeat file. Uses atomic_write for safety.

    Fields:
        agent_id: Unique agent identifier.
        role: Agent role (executor, escalation, etc.).
        state: One of starting|running|tool_call|exiting|error.
        activity: Human-readable description of current activity.
    """
    presence_dir = ACP_ROOT / "presence"
    presence_dir.mkdir(parents=True, exist_ok=True)
    path = presence_dir / f"{agent_id}.json"

    # Preserve original started_at if file already exists
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if path.exists():
        try:
            existing = load_json(path)
            if existing.get("started_at"):
                started_at = existing["started_at"]
        except Exception:
            pass

    record = {
        "agent_id": agent_id,
        "role": role,
        "state": state,
        "activity": activity,
        "pid": os.getpid(),
        "started_at": started_at,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    atomic_write(presence_dir, f"{agent_id}.json", record)


# ---------------------------------------------------------------------------
# Lock helpers
# ---------------------------------------------------------------------------

def lock_claim(message_path: Path) -> bool:
    """Atomically claim a message by creating <path>.lock/.

    Returns True if claim succeeded, False if already claimed.
    """
    lock_path = Path(f"{message_path}.lock")
    try:
        lock_path.mkdir(parents=False, exist_ok=False)
        return True
    except FileExistsError:
        return False
    except OSError:
        return False


def lock_release(message_path: Path) -> bool:
    """Release a lock by archiving <path>.lock/.

    Returns True if release succeeded, False if lock didn't exist.
    """
    lock_path = Path(f"{message_path}.lock")
    archive_dir = ARCHIVE / "released-locks" / datetime.now(timezone.utc).strftime("%Y%m%d")
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        target = archive_dir / lock_path.name
        if target.exists():
            target = archive_dir / f"{lock_path.name}.{uuid.uuid4().hex}"
        lock_path.replace(target)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def is_lock_stale(message_path: Path, max_age_seconds: int = 3600) -> bool:
    """Check if a lock directory is older than max_age_seconds."""
    lock_path = Path(f"{message_path}.lock")
    if not lock_path.is_dir():
        return False
    try:
        mtime = lock_path.stat().st_mtime
        return (time.time() - mtime) > max_age_seconds
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Run state management
# ---------------------------------------------------------------------------

def _run_dir(run_id: str) -> Path:
    return RUNS / run_id


def ensure_run_dir(run_id: str) -> Path:
    rd = _run_dir(run_id)
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "messages").mkdir(exist_ok=True)
    (rd / "artifacts").mkdir(exist_ok=True)
    return rd


def build_run_record(
    run_id: str,
    message_id: str = None,
    workflow_pattern: str = None,
    workspace: str = "home",
    state: str = "queued",
    current_step: str = None,
    blocked_reason: str = None,
    reply_to: str = None,
    parent_message_id: str = None,
    pending_input: dict = None,
    started_at: str = None,
    updated_at: str = None,
    ended_at: str = None,
    result_path: str = None,
    error_path: str = None,
    packet: dict = None,
    **extra,
) -> dict:
    """Build the durable workflow run record."""
    ts = _utc_now()
    record = {
        "run_id": run_id,
        "message_id": message_id,
        "workflow_pattern": workflow_pattern,
        "workspace": workspace,
        "state": state,
        "status": state,
        "current_step": current_step,
        "blocked_reason": blocked_reason,
        "reply_to": reply_to,
        "parent_message_id": parent_message_id,
        "pending_input": pending_input,
        "started_at": started_at or ts,
        "updated_at": updated_at or ts,
        "ended_at": ended_at,
        "result_path": result_path,
        "error_path": error_path,
    }
    if packet is not None:
        record["packet"] = packet
    for key, value in extra.items():
        if value is not None:
            record[key] = value
    return record


def normalize_run_record(data: dict, run_id: str = None) -> dict:
    """Normalize older run.json content into the canonical record shape."""
    if not isinstance(data, dict):
        data = {}
    rid = run_id or data.get("run_id") or "unknown"
    state = data.get("state") or data.get("status") or "queued"
    normalized = build_run_record(
        run_id=rid,
        message_id=data.get("message_id"),
        workflow_pattern=data.get("workflow_pattern") or data.get("pattern"),
        workspace=data.get("workspace", "home"),
        state=state,
        current_step=data.get("current_step"),
        blocked_reason=data.get("blocked_reason"),
        reply_to=data.get("reply_to"),
        parent_message_id=data.get("parent_message_id"),
        pending_input=data.get("pending_input"),
        started_at=data.get("started_at"),
        updated_at=data.get("updated_at"),
        ended_at=data.get("ended_at"),
        result_path=data.get("result_path"),
        error_path=data.get("error_path"),
        packet=data.get("packet"),
    )
    for key, value in data.items():
        if key not in normalized or normalized[key] is None:
            normalized[key] = value
    normalized["run_id"] = rid
    normalized["state"] = state
    normalized["status"] = state
    return normalized


def write_run_record(run_id: str, data: dict):
    """Write a normalized run.json for a run."""
    rd = ensure_run_dir(run_id)
    path = rd / "run.json"
    payload = normalize_run_record(data, run_id=run_id)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = TMP_DIR / f"{run_id}.run.json.{uuid.uuid4().hex}.tmp"
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)
    return path


def write_run_json(run_id: str, data: dict):
    """Write run.json for a run."""
    return write_run_record(run_id, data)


def read_run_json(run_id: str) -> dict | None:
    """Read run.json for a run. Returns None if not found."""
    path = _run_dir(run_id) / "run.json"
    if path.exists():
        return normalize_run_record(load_json(path), run_id=run_id)
    return None


def write_budget_json(run_id: str, data: dict):
    """Write budget.json for a run."""
    rd = ensure_run_dir(run_id)
    path = rd / "budget.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_budget_json(run_id: str) -> dict | None:
    """Read budget.json for a run."""
    path = _run_dir(run_id) / "budget.json"
    if path.exists():
        return load_json(path)
    return None


def update_run_state(run_id: str, status: str):
    """Update the status field in run.json for a run. Creates run.json if absent."""
    rd = ensure_run_dir(run_id)
    run_path = rd / "run.json"
    if run_path.exists():
        data = normalize_run_record(json.loads(run_path.read_text()), run_id=run_id)
    else:
        data = build_run_record(run_id=run_id, state=status)
    data["status"] = status
    data["state"] = status
    data["updated_at"] = _utc_now()
    if status in TERMINAL_RUN_STATES:
        data["ended_at"] = data.get("ended_at") or data["updated_at"]
    run_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def transition_run_state(
    run_id: str,
    to_state: str,
    *,
    step: str = None,
    message: str = None,
    source_message_id: str = None,
    blocked_reason: str = None,
    pending_input: dict = None,
    current_step: str = None,
    result_path: str = None,
    error_path: str = None,
    extra: dict = None,
) -> dict:
    """Persist a state transition and append a matching lifecycle event."""
    run_state = read_run_json(run_id) or {"run_id": run_id}
    from_state = run_state.get("state") or run_state.get("status") or "queued"
    # Terminal states are immutable.
    if from_state in TERMINAL_RUN_STATES and to_state != from_state:
        append_event(run_id, "state_transition_ignored", {
            "event": "state_transition_ignored",
            "from_state": from_state,
            "requested_state": to_state,
            "reason": "terminal_state_is_immutable",
            "message": message,
            "source_message_id": source_message_id,
        })
        return run_state
    if current_step is None:
        current_step = step if step is not None else run_state.get("current_step")

    updated = dict(run_state)
    updated["state"] = to_state
    updated["status"] = to_state
    updated["updated_at"] = _utc_now()
    if current_step is not None:
        updated["current_step"] = current_step
    if blocked_reason is not None or to_state in {"awaiting_input", "cancel_requested"}:
        updated["blocked_reason"] = blocked_reason
    if pending_input is not None or to_state == "awaiting_input":
        updated["pending_input"] = pending_input
    if result_path is not None:
        updated["result_path"] = result_path
    if error_path is not None:
        updated["error_path"] = error_path
    if to_state in TERMINAL_RUN_STATES:
        updated["ended_at"] = updated.get("ended_at") or updated["updated_at"]
    else:
        updated["ended_at"] = None
    if extra:
        updated.update({k: v for k, v in extra.items() if v is not None})

    write_run_record(run_id, updated)
    append_event(
        run_id,
        "state_changed",
        {
            "event": "state_changed",
            "from_state": from_state,
            "to_state": to_state,
            "step": current_step,
            "message": message,
            "source_message_id": source_message_id,
        },
    )
    return updated


def append_event(run_id: str, event_type: str, data: dict, agent_id: str | None = None):
    """Append event to per-run ledger and aggregate stream.

    Args:
        run_id: Unique run identifier.
        event_type: Type of event (state_changed, tool_call, etc.).
        data: Event payload dict.
        agent_id: Optional agent identifier (defaults to run_id).
    """
    rd = ensure_run_dir(run_id)
    path = rd / "events.jsonl"

    ts = datetime.now(timezone.utc).isoformat()

    # Unified flat schema — same entry written to both ledgers
    entry = {
        "run_id": run_id,
        "agent_id": agent_id or run_id,
        "timestamp": ts,
        "event": event_type,
        "event_type": event_type,
        **data,
    }

    # Per-run write (no lock needed — single writer per run)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Aggregate write (lock needed — concurrent writers from multiple agents)
    events_dir = ACP_ROOT / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    agg_path = events_dir / "current.jsonl"

    event_line = json.dumps(entry, ensure_ascii=False, default=str)
    with open(agg_path, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(event_line + "\n")
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def read_events(run_id: str, last_n: int = None) -> list:
    """Read events from events.jsonl. If last_n is set, return only the last N."""
    path = _run_dir(run_id) / "events.jsonl"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    if last_n:
        lines = lines[-last_n:]
    return [json.loads(line) for line in lines]


# ---------------------------------------------------------------------------
# Role resolution
# ---------------------------------------------------------------------------

def get_role_model(role_name: str) -> tuple:
    """Look up the first chain entry for a role from roles.toml.

    Returns (provider, model) tuple. Falls back to opencode/default.
    """
    try:
        with open(ROLES_TOML, "rb") as f:
            roles = tomllib.load(f)
    except Exception:
        return ("opencode", "default")

    role_config = roles.get(role_name, {})
    if not isinstance(role_config, dict):
        return ("opencode", "default")

    # Prefer explicit provider/model fields (OSS roles.toml format)
    provider = role_config.get("provider")
    model = role_config.get("model")
    if provider or model:
        return (provider or "opencode", model or "default")

    chain = role_config.get("chain", [])
    if chain:
        entry = chain[0]
        if ":" in entry:
            provider, model = entry.split(":", 1)
            return (provider, model)
        return ("opencode", entry)

    return ("opencode", "default")


def resolve_role(workspace: str, intent: str, fallback_role: str = "executor") -> str:
    """Resolve workspace+intent to a role name using the mapping table.

    Args:
        workspace: Workspace name (home, work, docs, scratch). Normalized automatically.
        intent: Packet intent (DOCS, SPEC, BUG, IMPLEMENT, etc.) or None.
        fallback_role: Role to return if no match found (default "executor").

    Returns:
        The resolved role name.
    """
    workspace = normalize_workspace(workspace)
    key = (workspace, intent)
    role = WORKSPACE_INTENT_ROLE.get(key)
    if role:
        return role
    if intent == "HELP":
        return "escalation"
    return fallback_role


def validate_workflow_block(packet: dict) -> list:
    """Validate an optional packet.workflow block.

    Returns a list of error strings. Empty list = valid.
    """
    errors = []
    workflow = packet.get("workflow") if isinstance(packet, dict) else None

    if workflow is None:
        return errors  # Optional block, absent is valid

    if not isinstance(workflow, dict):
        errors.append("packet.workflow must be a dict if present")
        return errors

    # pattern is required when workflow block is present
    pattern = workflow.get("pattern")
    if not pattern or not isinstance(pattern, str):
        errors.append("packet.workflow.pattern is required and must be a string")
    elif pattern not in VALID_WORKFLOW_PATTERNS:
        valid = sorted(VALID_WORKFLOW_PATTERNS)
        errors.append(f"Invalid workflow pattern {pattern!r}. Must be one of {valid}")

    # task is required
    task = workflow.get("task")
    if not task or not isinstance(task, str) or not task.strip():
        errors.append("packet.workflow.task is required and must be a non-empty string")

    # agents (swarm only, but validate globally)
    agents = workflow.get("agents", 3)
    if not isinstance(agents, int) or agents < 1 or agents > 5:
        errors.append("packet.workflow.agents must be an integer between 1 and 5")

    # timeout_seconds
    timeout = workflow.get("timeout_seconds")
    if timeout is not None:
        if not isinstance(timeout, int) or timeout <= 0 or timeout > 7200:
            errors.append("packet.workflow.timeout_seconds must be an integer 1-7200")

    # goal_file must be under ACP run dir if present
    goal_file = workflow.get("goal_file")
    if goal_file is not None:
        if not isinstance(goal_file, str):
            errors.append("packet.workflow.goal_file must be a string or null")

    # mode validation
    mode = workflow.get("mode")
    if mode is not None and mode not in ("async", "sync"):
        errors.append("packet.workflow.mode must be 'async' or 'sync'")

    # memory must be boolean if present
    memory = workflow.get("memory")
    if memory is not None and not isinstance(memory, bool):
        errors.append("packet.workflow.memory must be a boolean if present")

    # expected_artifacts must be a list of strings
    artifacts = workflow.get("expected_artifacts")
    if artifacts is not None:
        if not isinstance(artifacts, list):
            errors.append("packet.workflow.expected_artifacts must be a list")
        else:
            for i, a in enumerate(artifacts):
                if not isinstance(a, str):
                    errors.append(f"packet.workflow.expected_artifacts[{i}] must be a string")

    return errors


# ---------------------------------------------------------------------------
# Budget checking
# ---------------------------------------------------------------------------

def read_budget_toml() -> dict:
    """Read the ACP role-scoped budget.toml. Returns dict of role -> cost class.

    Budget file is optional in OSS; missing file returns {}.
    """
    try:
        with open(ACP_BUDGET_TOML, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def check_budget(message: dict) -> tuple:
    """Check if a message's budget block allows dispatch.

    Returns (ok: bool, reason: str).
    """
    budget = message.get("budget", {})
    cost_class = budget.get("cost_class", "free")
    allow_paid = budget.get("allow_paid", False)
    max_usd = budget.get("max_usd", 0.0)
    reserved_usd = budget.get("reserved_usd", 0.0)

    # If cost_class is "paid" and allow_paid is False, reject
    if cost_class == "paid" and not allow_paid:
        return (False, "Paid cost class requires allow_paid=true")

    # max_usd <= 0 means "no USD limit". Only enforce a ceiling when positive.
    if max_usd > 0 and reserved_usd > max_usd:
        return (False, f"Reserved ${reserved_usd:.2f} exceeds max ${max_usd:.2f}")

    return (True, "ok")


# ---------------------------------------------------------------------------
# Inbox routing
# ---------------------------------------------------------------------------

def resolve_inbox(message: dict) -> Path:
    """Resolve the target inbox for a message based on routing rules.

    Returns the inbox Path, or writes to dead-letter path if no route found.
    """
    to = message.get("to", {})
    intent = message.get("intent", "")

    # Rule 1: to.agent_id present → agents/<agent_id>/
    agent_id = to.get("agent_id")
    if agent_id:
        inbox = INBOX_AGENTS / agent_id
        inbox.mkdir(parents=True, exist_ok=True)
        return inbox

    # Rule 2: HELP intent → HELP routing
    if intent == "HELP":
        packet = message.get("packet", {})
        parent_agent = packet.get("parent_agent") if isinstance(packet, dict) else None
        if parent_agent:
            parent_inbox = INBOX_AGENTS / parent_agent
            if parent_inbox.exists():
                return parent_inbox
        return INBOX_ORCHESTRATOR

    # Rule 3: to.workspace → workspaces/<workspace>/
    workspace = to.get("workspace")
    workspace = normalize_workspace(workspace)
    if workspace in GENERIC_WORKSPACES:
        inbox = INBOX_WORKSPACES / workspace
        inbox.mkdir(parents=True, exist_ok=True)
        return inbox

    # Rule 4: to.role present, no workspace → router/
    role = to.get("role")
    if role:
        return INBOX_ROUTER

    # Rule 5: no match → dead-letter
    return DEAD_LETTER
