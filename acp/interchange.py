#!/usr/bin/env python3
"""ACP Interchange — universal agent-to-agent invocation facade.

Provides both an importable Python API and a CLI for dispatching ACP tasks
with explicit agent targeting, role-based resolution, and result retrieval.

Usage:
    # As a module
    from acp.interchange import dispatch, status, await_result, result

    req = InterchangeRequest(
        caller_agent_id="orchestrator",
        target_agent_id="claude",
        workspace="home",
        objective="Review this PR"
    )
    handle = dispatch(req)

    # As a CLI
    python3 -m acp.interchange dispatch --target-agent-id claude \\
        --objective "Review this PR" --json
    python3 -m acp.interchange status <run_id> --json
    python3 -m acp.interchange await <run_id> --json
    python3 -m acp.interchange result <run_id> --json
    python3 -m acp.interchange resolve --agent-id claude --json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Interchange depth limit ──────────────────────────────────────────────────

INTERCHANGE_MAX_DEPTH = int(os.environ.get("AGENT_OS_INTERCHANGE_MAX_DEPTH", "3"))

# ── Paths ──────────────────────────────────────────────────────────────────────

_HOME = Path(os.environ.get("HOME", os.path.expanduser("~"))).expanduser()
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent  # .../repo when package lives at repo/acp

def _detect_agent_os_home() -> Path:
    env = os.environ.get("AGENT_OS_HOME")
    if env:
        return Path(env).expanduser()
    # Dev layout: package is at <root>/acp and workflows live under <root>/.config
    if (_REPO_ROOT / ".config" / "agent-workflows" / "acp" / "acp_common.py").exists():
        return _REPO_ROOT
    return _HOME / "agent-os"


AGENT_OS_HOME = _detect_agent_os_home()

# Prefer install-root workflows, then repo-relative fallback
_ACP_CANDIDATES = [
    AGENT_OS_HOME / ".config" / "agent-workflows" / "acp",
    _REPO_ROOT / ".config" / "agent-workflows" / "acp",
]
ACP_DIR = next(
    (d for d in _ACP_CANDIDATES if (d / "acp_common.py").exists()),
    _ACP_CANDIDATES[0],
)
ACP_ROOT = Path(
    os.environ.get(
        "AGENT_OS_ACP_ROOT",
        str(AGENT_OS_HOME / ".local" / "state" / "agent-os" / "acp"),
    )
).expanduser()
RUNS_DIR = ACP_ROOT / "runs"

# Prefer package-local send.py; fall back to install layout
SEND_PY = _THIS_DIR / "send.py"
if not SEND_PY.exists():
    SEND_PY = AGENT_OS_HOME / "acp" / "send.py"

# Ensure acp_common is importable
sys.path.insert(0, str(ACP_DIR))
import acp_common  # noqa: E402

# Make interchange_resolver importable (same package dir)
sys.path.insert(0, str(_THIS_DIR))


# ── Data classes (§3) ──────────────────────────────────────────────────────────

SCHEMA_HANDLE = "agent.os.interchange.handle.v1"
SCHEMA_RESULT = "agent.os.interchange.result.v1"


@dataclass(frozen=True)
class InterchangeRequest:
    """Complete interchange invocation request."""

    caller_agent_id: str
    target_agent_id: Optional[str] = None
    workspace: str = "home"
    objective: str = ""
    requested_role: Optional[str] = None
    caller_role: Optional[str] = None
    caller_provider: Optional[str] = None
    caller_model: Optional[str] = None
    parent_run_id: Optional[str] = None
    model: Optional[str] = None
    reasoning: Optional[str] = None
    mode: str = "oneshot"  # oneshot | persistent
    session_id: Optional[str] = None
    session_name: Optional[str] = None
    return_mode: str = "sync"  # sync | async
    wait_timeout_seconds: int = 1800
    allow_paid: bool = False
    max_cost_usd: float = 0.0
    token_cap: int = 12000
    memory: bool = True
    notify_via_agent_mail: bool = False


@dataclass(frozen=True)
class DispatchHandle:
    """Lightweight handle returned immediately after dispatch.

    Schema: agent.os.interchange.handle.v1
    """

    schema: str = SCHEMA_HANDLE
    run_id: str = ""
    state: str = "queued"  # queued | running | terminal
    caller_agent_id: str = ""
    target_agent_id: str = ""
    requested_role: Optional[str] = None
    resolved_role: str = ""
    resolved_provider: str = ""
    resolved_model: str = ""
    mode: str = "oneshot"
    return_mode: str = "sync"
    session_id: Optional[str] = None
    receipt_path: Optional[str] = None


@dataclass(frozen=True)
class DispatchResult:
    """Complete result after synchronous completion.

    Schema: agent.os.interchange.result.v1
    """

    schema: str = SCHEMA_RESULT
    handle: Optional[DispatchHandle] = None
    completion: Optional[dict] = None
    receipt: Optional[dict] = None
    output_path: Optional[str] = None
    output_summary: str = ""


# ── Nested sync guard ──────────────────────────────────────────────────────────

NESTED_SYNC_ERROR = {
    "error": "nested_sync_unsupported",
    "message": "Use return_mode=async and retrieve the child result on a later turn.",
    "safe_return_mode": "async",
}


def _check_nested_sync(return_mode: str) -> None:
    """Reject synchronous dispatch when running inside an ACP daemon worker."""
    active_run_id = os.environ.get("AGENT_OS_ACP_ACTIVE_RUN_ID", "")
    if active_run_id and return_mode == "sync":
        error = dict(NESTED_SYNC_ERROR)
        error["parent_run_id"] = active_run_id
        print(json.dumps(error, indent=2), file=sys.stderr)
        sys.exit(1)


# ── Caller identity helpers ─────────────────────────────────────────────────────


def _derive_caller_identity() -> dict:
    """Derive caller identity from trusted environment or defaults."""
    env_id = os.environ.get("AGENT_OS_AGENT_ID")
    return {
        "caller_agent_id": env_id or "worker",
        "caller_role": os.environ.get("AGENT_OS_AGENT_ROLE") or "unknown",
        "caller_provider": os.environ.get("AGENT_OS_AGENT_PROVIDER") or "unknown",
        "caller_model": os.environ.get("AGENT_OS_AGENT_MODEL") or "unknown",
        "caller_identity_source": "trusted" if env_id else "declared",
    }


def _derive_parent_run_id() -> Optional[str]:
    """Derive parent_run_id from AGENT_OS_ACP_ACTIVE_RUN_ID."""
    return os.environ.get("AGENT_OS_ACP_ACTIVE_RUN_ID") or None


def _get_interchange_depth() -> int:
    """Get current interchange depth from environment."""
    return int(os.environ.get("AGENT_OS_INTERCHANGE_DEPTH", "0"))


def _get_interchange_ancestry() -> list:
    """Get current interchange ancestry from environment."""
    raw = os.environ.get("AGENT_OS_INTERCHANGE_ANCESTRY", "")
    return raw.split(",") if raw else []


# ── Route resolution ────────────────────────────────────────────────────────────


def _resolve_target(req: InterchangeRequest) -> object:
    """Resolve target agent via interchange_resolver."""
    from interchange_resolver import (
        resolve_explicit_agent,
        resolve_role_selected,
    )

    if req.target_agent_id:
        return resolve_explicit_agent(
            target_agent_id=req.target_agent_id,
            requested_role=req.requested_role,
            requested_model=req.model,
        )
    else:
        if not req.requested_role:
            raise ValueError(
                "requested_role is required when target_agent_id is not set"
            )
        return resolve_role_selected(
            requested_role=req.requested_role,
            requested_model=req.model,
        )


# ── Public API: dispatch ────────────────────────────────────────────────────────


def dispatch(
    req: InterchangeRequest,
    route: Optional[object] = None,
) -> DispatchHandle:
    """Dispatch an interchange request and return a DispatchHandle.

    Fire-and-forget: resolves target, enqueues via send.py, returns handle.
    """
    # ── Nested sync guard (before any side effects) ────────────────────────
    _check_nested_sync(req.return_mode)

    # ── Resolve target ────────────────────────────────────────────────────
    if route is None:
        route = _resolve_target(req)

    # ── Derive identity ───────────────────────────────────────────────────
    identity = _derive_caller_identity()
    trusted_fields = {
        "caller_agent_id": ("AGENT_OS_AGENT_ID", req.caller_agent_id),
        "caller_role": ("AGENT_OS_AGENT_ROLE", req.caller_role),
        "caller_provider": ("AGENT_OS_AGENT_PROVIDER", req.caller_provider),
        "caller_model": ("AGENT_OS_AGENT_MODEL", req.caller_model),
    }
    for field, (env_name, declared) in trusted_fields.items():
        trusted = os.environ.get(env_name)
        if trusted and declared and trusted != declared:
            raise ValueError(
                f"{field}={declared!r} conflicts with trusted {env_name}={trusted!r}"
            )
    trusted_parent = _derive_parent_run_id()
    if trusted_parent and req.parent_run_id and trusted_parent != req.parent_run_id:
        raise ValueError(
            f"parent_run_id={req.parent_run_id!r} conflicts with trusted "
            f"AGENT_OS_ACP_ACTIVE_RUN_ID={trusted_parent!r}"
        )
    parent_run_id = trusted_parent or req.parent_run_id

    target_agent_id = route.target_agent_id
    resolved_role = route.resolved_role
    resolved_provider = route.resolved_provider
    resolved_model = route.resolved_model

    if req.mode == "persistent":
        try:
            from acpx_session_ledger import create_session, show_session  # type: ignore
        except ImportError as exc:
            raise ValueError(
                "Persistent mode requires acpx_session_ledger (not ported in OSS MVP). "
                "Use mode=oneshot."
            ) from exc

        if req.session_id:
            session_record = show_session(req.session_id)
            if not session_record or session_record.get("status") != "active":
                raise ValueError(
                    f"Persistent session {req.session_id!r} is not active"
                )
        else:
            created_session_id = create_session(req, route)
            session_record = show_session(created_session_id)
            if not session_record:
                raise RuntimeError(
                    f"Session ledger did not persist {created_session_id}"
                )
        req = replace(
            req,
            session_id=session_record["session_id"],
            session_name=session_record["adapter_session_name"],
        )

    # ── Depth / ancestry / cycle checks ───────────────────────────────────
    current_depth = _get_interchange_depth()
    ancestry = _get_interchange_ancestry()
    effective_caller = (
        identity["caller_agent_id"]
        if os.environ.get("AGENT_OS_AGENT_ID")
        else req.caller_agent_id or identity["caller_agent_id"]
    )
    if not ancestry or ancestry[-1] != effective_caller:
        ancestry = ancestry + [effective_caller]

    if target_agent_id in ancestry:
        raise ValueError(
            f"Cycle detected: target '{target_agent_id}' already in ancestry "
            f"{ancestry}."
        )

    if current_depth >= INTERCHANGE_MAX_DEPTH:
        raise ValueError(
            f"Max interchange depth ({INTERCHANGE_MAX_DEPTH}) reached. "
            f"Increase AGENT_OS_INTERCHANGE_MAX_DEPTH or reduce call chain."
        )

    # ── Budget / deadline propagation from parent ─────────────────────────
    child_timeout = req.wait_timeout_seconds
    child_max_cost = req.max_cost_usd
    child_token_cap = req.token_cap

    if parent_run_id:
        parent_run_dir = RUNS_DIR / parent_run_id
        budget_path = parent_run_dir / "budget.json"
        if budget_path.exists():
            try:
                parent_budget = json.loads(budget_path.read_text())
                parent_remaining = parent_budget.get("max_usd", 0.0) - parent_budget.get(
                    "spent_usd", 0.0
                )
                if req.allow_paid and not parent_budget.get("allow_paid", False):
                    raise ValueError("Parent run does not permit paid child dispatch")
                if child_max_cost <= 0 or child_max_cost > parent_remaining:
                    child_max_cost = max(0.0, parent_remaining)
                parent_token_cap = parent_budget.get("token_cap", 12000)
                if child_token_cap > parent_token_cap:
                    child_token_cap = parent_token_cap
            except (json.JSONDecodeError, OSError) as exc:
                raise ValueError(f"Cannot read parent budget safely: {exc}") from exc
        elif req.allow_paid or req.max_cost_usd > 0:
            raise ValueError(
                "Parent budget is missing; paid child dispatch is not allowed"
            )

        run_path = parent_run_dir / "run.json"
        if run_path.exists():
            try:
                parent_run = json.loads(run_path.read_text())
                parent_timeout = parent_run.get("timeout_seconds", 1800)
                created_at = parent_run.get("created_at") or parent_run.get(
                    "started_at"
                )
                remaining = parent_timeout
                if created_at:
                    started = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )
                    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                    remaining = max(1, int(parent_timeout - elapsed))
                child_timeout = min(child_timeout, remaining)
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                raise ValueError(
                    f"Cannot derive parent deadline safely: {exc}"
                ) from exc

    # ── Build send.py command ─────────────────────────────────────────────
    send_args = [
        sys.executable,
        str(SEND_PY),
        "--objective",
        req.objective,
        "--workspace",
        req.workspace,
        "--mode",
        req.mode,
        "--return-mode",
        req.return_mode,
        "--caller-agent-id",
        identity["caller_agent_id"]
        if os.environ.get("AGENT_OS_AGENT_ID")
        else req.caller_agent_id or identity["caller_agent_id"],
        "--caller-role",
        identity["caller_role"]
        if os.environ.get("AGENT_OS_AGENT_ROLE")
        else req.caller_role or identity["caller_role"],
        "--caller-provider",
        identity["caller_provider"]
        if os.environ.get("AGENT_OS_AGENT_PROVIDER")
        else req.caller_provider or identity["caller_provider"],
        "--caller-model",
        identity["caller_model"]
        if os.environ.get("AGENT_OS_AGENT_MODEL")
        else req.caller_model or identity["caller_model"],
        "--target-agent-id",
        target_agent_id,
        "--print-run-id",
    ]
    if resolved_model:
        send_args.extend(["--model", resolved_model])
        if req.model:
            send_args.append("--strict-model")
    if resolved_provider:
        send_args.extend(["--provider", resolved_provider])

    if req.requested_role:
        send_args.extend(["--requested-role", req.requested_role])
    if parent_run_id:
        send_args.extend(["--parent-run-id", parent_run_id])
    if req.allow_paid:
        send_args.append("--allow-paid")
    if child_max_cost > 0:
        send_args.extend(["--max-cost-usd", str(child_max_cost)])
    send_args.extend(["--token-cap", str(child_token_cap)])
    if child_timeout != 1800:
        send_args.extend(["--wait-timeout", str(child_timeout)])
    if not req.memory:
        send_args.append("--no-memory")
    if req.notify_via_agent_mail:
        send_args.append("--notify-via-agent-mail")
    if req.session_name:
        send_args.extend(["--session", req.session_name])
    dispatch_env = os.environ.copy()
    dispatch_env["AGENT_OS_INTERCHANGE_DEPTH"] = str(current_depth + 1)
    dispatch_env["AGENT_OS_INTERCHANGE_ANCESTRY"] = ",".join(
        ancestry + [target_agent_id]
    )
    dispatch_env.setdefault("AGENT_OS_HOME", str(AGENT_OS_HOME))
    dispatch_env.setdefault("AGENT_OS_ACP_ROOT", str(ACP_ROOT))

    # ── Dispatch ──────────────────────────────────────────────────────────
    result_proc = subprocess.run(
        send_args, capture_output=True, text=True, env=dispatch_env
    )

    if result_proc.returncode != 0:
        if result_proc.stderr:
            print(result_proc.stderr, file=sys.stderr, end="")
        if result_proc.stdout:
            print(result_proc.stdout, file=sys.stderr, end="")
        sys.exit(result_proc.returncode)

    run_id = ""
    for line in result_proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("RUN_ID="):
            run_id = line.split("=", 1)[1].strip()
            break

    if not run_id:
        print(
            "ACP_INTERCHANGE: ERROR — could not extract RUN_ID from send.py output",
            file=sys.stderr,
        )
        print(result_proc.stdout, file=sys.stderr)
        sys.exit(1)

    if req.mode == "persistent" and req.session_id:
        try:
            from acpx_session_ledger import continue_session  # type: ignore

            continue_session(
                req.session_id, req.objective, req.return_mode == "async", run_id
            )
        except ImportError:
            pass

    return DispatchHandle(
        run_id=run_id,
        state="queued",
        caller_agent_id=identity["caller_agent_id"]
        if os.environ.get("AGENT_OS_AGENT_ID")
        else req.caller_agent_id or identity["caller_agent_id"],
        target_agent_id=target_agent_id,
        requested_role=req.requested_role,
        resolved_role=resolved_role,
        resolved_provider=resolved_provider,
        resolved_model=resolved_model,
        mode=req.mode,
        return_mode=req.return_mode,
        session_id=req.session_id,
    )


# ── Public API: status ──────────────────────────────────────────────────────────


def status(run_id: str) -> dict:
    """Read current run state from run.json (falls back to envelope.json)."""
    run_path = RUNS_DIR / run_id / "run.json"
    if run_path.exists():
        try:
            return json.loads(run_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return {"run_id": run_id, "error": "read_failed", "detail": str(exc)}

    env_path = RUNS_DIR / run_id / "envelope.json"
    if env_path.exists():
        try:
            data = json.loads(env_path.read_text(encoding="utf-8"))
            return {
                "run_id": run_id,
                "state": data.get("state", "unknown"),
                "status": data.get("state", "unknown"),
                "workspace": data.get("workspace"),
            }
        except (json.JSONDecodeError, OSError) as exc:
            return {"run_id": run_id, "error": "read_failed", "detail": str(exc)}

    return {"run_id": run_id, "error": "run_not_found", "status": "unknown"}


# ── Public API: await_result ────────────────────────────────────────────────────


def await_result(run_id: str, timeout: int = 1800) -> dict:
    """Wait for a run to reach a terminal state.

    Polls run.json / envelope.json. Uses acp_wait.py when present; otherwise
    polls inline (OSS MVP — acp_wait.py is deferred).
    """
    wait_script = ACP_DIR / "acp_wait.py"
    if wait_script.exists():
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(wait_script),
                    run_id,
                    "--timeout",
                    str(timeout),
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=timeout + 60,
            )
        except subprocess.TimeoutExpired:
            return {
                "run_id": run_id,
                "error": "timeout",
                "message": f"acp_wait.py exceeded {timeout}s + 60s grace period",
            }
        if proc.stderr:
            print(proc.stderr, file=sys.stderr, end="")
        if proc.stdout:
            try:
                return json.loads(proc.stdout)
            except (json.JSONDecodeError, ValueError):
                pass
        return {
            "run_id": run_id,
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }

    # Inline poll
    terminal = acp_common.TERMINAL_RUN_STATES
    deadline = time.time() + max(1, timeout)
    last_state = "unknown"
    while time.time() < deadline:
        data = status(run_id)
        last_state = data.get("state") or data.get("status") or "unknown"
        if last_state in terminal:
            return {
                "run_id": run_id,
                "state": last_state,
                "status": last_state,
            }
        if data.get("error") == "run_not_found":
            return data
        time.sleep(1)

    return {
        "run_id": run_id,
        "error": "timeout",
        "state": last_state,
        "message": f"Timed out after {timeout}s waiting for terminal state",
    }


# ── Public API: result ──────────────────────────────────────────────────────────


def result(run_id: str) -> dict:
    """Read the authoritative result for a completed run."""
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return {"run_id": run_id, "error": "run_not_found"}

    run_state = status(run_id)

    receipt_path_obj = run_dir / "receipt.json"
    receipt_data = None
    if receipt_path_obj.exists():
        try:
            receipt_data = json.loads(receipt_path_obj.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            receipt_data = {"error": "receipt_read_failed", "detail": str(exc)}

    events_path = run_dir / "events.jsonl"
    events = []
    if events_path.exists():
        try:
            for line in events_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        except (json.JSONDecodeError, OSError):
            pass

    output_path_str = None
    try:
        artifacts_dir = run_dir / "artifacts"
        for entry in sorted(artifacts_dir.iterdir()) if artifacts_dir.is_dir() else []:
            name = entry.name
            if name.startswith("output_") and ".err" not in name:
                output_path_str = str(entry)
                break
    except OSError:
        pass

    output_summary = ""
    if output_path_str:
        try:
            text = Path(output_path_str).read_text(
                encoding="utf-8", errors="replace"
            )
            output_summary = text[:500] if len(text) > 500 else text
        except OSError:
            pass

    return {
        "run_id": run_id,
        "state": run_state.get("state") or run_state.get("status", "unknown"),
        "receipt": receipt_data,
        "events": events,
        "output_path": output_path_str,
        "output_summary": output_summary,
    }


# ── Convenience: dispatch and wait ──────────────────────────────────────────────


def dispatch_and_wait(req: InterchangeRequest) -> DispatchResult:
    """Dispatch a request and wait for completion."""
    handle = dispatch(req)
    completion = await_result(handle.run_id, req.wait_timeout_seconds)
    result_data = result(handle.run_id)

    return DispatchResult(
        handle=handle,
        completion=completion,
        receipt=result_data.get("receipt") or {},
        output_path=result_data.get("output_path"),
        output_summary=result_data.get("output_summary", ""),
    )


# ── CLI handlers ────────────────────────────────────────────────────────────────


def cli_dispatch(args: argparse.Namespace) -> None:
    """CLI handler for `dispatch` subcommand."""
    try:
        _check_nested_sync(args.return_mode)

        req = InterchangeRequest(
            caller_agent_id=args.caller_agent_id or "",
            target_agent_id=args.target_agent_id,
            workspace=args.workspace,
            objective=args.objective,
            requested_role=args.requested_role,
            caller_role=args.caller_role,
            caller_provider=args.caller_provider,
            caller_model=args.caller_model,
            parent_run_id=args.parent_run_id,
            model=args.model,
            mode=args.mode,
            session_name=args.session_name,
            return_mode=args.return_mode,
            wait_timeout_seconds=args.wait_timeout,
            allow_paid=args.allow_paid,
            max_cost_usd=args.max_cost_usd,
            token_cap=args.token_cap,
            memory=not args.no_memory,
            notify_via_agent_mail=args.notify_via_agent_mail,
        )

        if args.return_mode == "sync" or args.wait:
            dr = dispatch_and_wait(req)
            if args.json:
                print(json.dumps(asdict(dr), indent=2, default=str))
            else:
                handle = dr.handle
                print(f"Run:      {handle.run_id}")
                print(f"Target:   {handle.target_agent_id} ({handle.resolved_role})")
                print(f"Model:    {handle.resolved_model}")
                print(f"Provider: {handle.resolved_provider}")
                print(f"State:    {handle.state}")
                if dr.completion:
                    cs = dr.completion.get(
                        "state", dr.completion.get("error", "unknown")
                    )
                    print(f"Final:    {cs}")
                if dr.receipt and not dr.receipt.get("error"):
                    print(f"Receipt:  {dr.receipt.get('receipt_id', 'N/A')}")
                if dr.output_path:
                    print(f"Output:   {dr.output_path}")
        else:
            handle = dispatch(req)
            if args.json:
                print(json.dumps(asdict(handle), indent=2, default=str))
            else:
                print(f"Run:      {handle.run_id}")
                print(f"Target:   {handle.target_agent_id} ({handle.resolved_role})")
                print(f"Model:    {handle.resolved_model}")
                print(f"Provider: {handle.resolved_provider}")
                print(f"Mode:     {handle.mode}, return: {handle.return_mode}")
    except (ValueError, FileNotFoundError, ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def cli_status(args: argparse.Namespace) -> None:
    """CLI handler for `status` subcommand."""
    data = status(args.run_id)
    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        state_val = data.get("status") or data.get("state") or data.get(
            "error", "unknown"
        )
        print(f"Run:   {args.run_id}")
        print(f"State: {state_val}")
        if data.get("error"):
            print(f"Error: {data['error']}", file=sys.stderr)


def cli_await(args: argparse.Namespace) -> None:
    """CLI handler for `await` subcommand."""
    data = await_result(args.run_id, args.timeout)
    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        state_val = data.get("state") or data.get("error", "unknown")
        print(f"Run {args.run_id}: {state_val}")


def cli_result(args: argparse.Namespace) -> None:
    """CLI handler for `result` subcommand."""
    data = result(args.run_id)
    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        state_val = data.get("state", "unknown")
        print(f"Run:      {args.run_id}")
        print(f"State:    {state_val}")
        rcp = data.get("receipt")
        if rcp and not rcp.get("error"):
            print(f"Receipt:  {rcp.get('receipt_id', 'N/A')}")
            print(f"Outcome:  {rcp.get('outcome', 'N/A')}")
        else:
            print(f"Receipt:  {rcp}")
        if data.get("output_path"):
            print(f"Output:   {data['output_path']}")


def cli_resolve(args: argparse.Namespace) -> None:
    """CLI handler for `resolve` subcommand."""
    from interchange_resolver import (
        resolve_explicit_agent,
        resolve_role_selected,
    )

    try:
        if args.agent_id:
            route = resolve_explicit_agent(
                target_agent_id=args.agent_id,
                requested_role=args.role,
                requested_model=args.model,
                strict_model=not getattr(args, "no_strict", False),
            )
        elif args.role:
            route = resolve_role_selected(
                requested_role=args.role,
                requested_model=args.model,
            )
        else:
            print("ERROR: specify --agent-id or --role", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(asdict(route), indent=2))
        else:
            print(f"target_agent_id:   {route.target_agent_id}")
            print(f"resolved_role:     {route.resolved_role}")
            print(f"resolved_provider: {route.resolved_provider}")
            print(f"resolved_model:    {route.resolved_model}")
            print(f"requested_role:    {route.requested_role}")
            print(f"requested_model:   {route.requested_model}")
            print(f"model_source:      {route.model_source}")
    except (ValueError, FileNotFoundError, ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def cli_session(args: argparse.Namespace) -> None:
    """Handle session subcommands (optional — requires acpx_session_ledger)."""
    try:
        from acpx_session_ledger import (  # type: ignore
            create_session,
            show_session,
            close_session,
            reconcile_sessions,
        )
    except ImportError:
        print(
            "ERROR: session management requires acpx_session_ledger "
            "(not ported in OSS MVP).",
            file=sys.stderr,
        )
        sys.exit(1)

    from interchange_resolver import (
        resolve_explicit_agent,
        resolve_role_selected,
    )

    if args.session_action == "create":
        if args.target_agent_id:
            route = resolve_explicit_agent(
                args.target_agent_id, args.requested_role, args.model
            )
        else:
            route = resolve_role_selected(args.requested_role, args.model)

        req = InterchangeRequest(
            caller_agent_id=args.caller_agent_id or "unknown",
            target_agent_id=route.target_agent_id,
            workspace=args.workspace,
            objective=args.objective or "",
            requested_role=route.requested_role,
            mode="persistent",
            session_name=args.session_name,
            model=route.resolved_model,
        )

        session_id = create_session(req, route)
        sess = show_session(session_id) or {"session_id": session_id}
        if args.json:
            print(json.dumps(sess, indent=2, default=str))
        else:
            print(f"session_id: {sess['session_id']}")
            print(f"display_name: {sess.get('display_name', '')}")
            print(f"adapter_session_name: {sess.get('adapter_session_name', '')}")
        return

    elif args.session_action == "show":
        sess = show_session(args.session_id)
    elif args.session_action == "continue":
        record = show_session(args.session_id)
        if record is None:
            print(f"ERROR: session '{args.session_id}' not found", file=sys.stderr)
            sys.exit(1)
        if record.get("status") != "active":
            print(
                f"ERROR: session '{args.session_id}' is {record.get('status')}, "
                "not active",
                file=sys.stderr,
            )
            sys.exit(1)

        req = InterchangeRequest(
            caller_agent_id=record.get("caller_agent_id", "unknown"),
            target_agent_id=record.get("target_agent_id"),
            workspace=record.get("workspace", "home"),
            objective=args.objective,
            requested_role=record.get("requested_role"),
            mode="persistent",
            return_mode="async" if args.is_async else "sync",
            session_id=args.session_id,
            session_name=record.get("display_name"),
            model=record.get("model"),
        )
        route = _resolve_target(req)
        completed = None
        if args.is_async:
            handle = dispatch(req, route)
        else:
            completed = dispatch_and_wait(req)
            handle = completed.handle
        sess = show_session(args.session_id) or {}
        sess["run_id"] = handle.run_id
        sess["state"] = handle.state
        sess["target_agent_id"] = handle.target_agent_id
        if completed:
            sess["completion"] = completed.completion
            sess["receipt"] = completed.receipt
            sess["output_path"] = completed.output_path
            sess["output_summary"] = completed.output_summary
    elif args.session_action == "close":
        sess = close_session(args.session_id)
    elif args.session_action == "reconcile":
        sess = reconcile_sessions(args.all)
    else:
        print(f"ERROR: unknown session action {args.session_action}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(sess, indent=2, default=str))
    else:
        if isinstance(sess, dict):
            for k, v in sess.items():
                print(f"{k}: {v}")
        else:
            print(sess)


# ── CLI argument parser ─────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the interchange CLI."""
    parser = argparse.ArgumentParser(
        description="ACP Interchange — universal agent-to-agent invocation facade",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Machine-readable output (--json) goes to stdout;\n"
            "diagnostics and progress messages go to stderr.\n"
            "\n"
            "Subcommands:\n"
            "  dispatch  Dispatch an interchange task\n"
            "  status    Get run state from run.json\n"
            "  await     Wait for run completion\n"
            "  result    Read receipt and output artifacts\n"
            "  resolve   Resolve agent/role to an execution route\n"
            "  session   Manage persistent agent sessions (optional)"
        ),
    )

    subparsers = parser.add_subparsers(dest="command", help="Subcommand")
    _add_dispatch_parser(subparsers)
    _add_status_parser(subparsers)
    _add_await_parser(subparsers)
    _add_result_parser(subparsers)
    _add_resolve_parser(subparsers)
    _add_session_subparser(subparsers)

    return parser


def _add_dispatch_parser(subparsers) -> None:
    p = subparsers.add_parser("dispatch", help="Dispatch an interchange task")
    p.add_argument("--caller-agent-id", default=None, help="Caller agent ID")
    p.add_argument("--caller-role", default=None, help="Caller's current role")
    p.add_argument("--caller-provider", default=None, help="Caller's provider")
    p.add_argument("--caller-model", default=None, help="Caller's model identifier")
    p.add_argument(
        "--target-agent-id",
        default=None,
        help="Explicit target agent ID (resolved directly)",
    )
    p.add_argument(
        "--requested-role",
        default=None,
        help="Behavioral role requested of the target",
    )
    p.add_argument("--workspace", default="home", help="Target workspace")
    p.add_argument("--objective", required=True, help="Task objective text")
    p.add_argument("--model", default=None, help="Explicit model override")
    p.add_argument(
        "--mode",
        default="oneshot",
        choices=["oneshot", "persistent"],
        help="Execution mode (default: oneshot)",
    )
    p.add_argument(
        "--session-name", default=None, help="Named session for persistent mode"
    )
    p.add_argument(
        "--return-mode",
        default="sync",
        choices=["sync", "async"],
        help="Return mode (default: sync)",
    )
    p.add_argument(
        "--wait",
        action="store_true",
        help="Wait for completion (implies dispatch_and_wait)",
    )
    p.add_argument(
        "--wait-timeout",
        type=int,
        default=1800,
        help="Timeout in seconds for wait (default: 1800)",
    )
    p.add_argument("--allow-paid", action="store_true", help="Allow paid cost class")
    p.add_argument(
        "--max-cost-usd", type=float, default=0.0, help="Max cost in USD"
    )
    p.add_argument(
        "--token-cap", type=int, default=12000, help="Token cap (default: 12000)"
    )
    p.add_argument("--no-memory", action="store_true", help="Disable memory injection")
    p.add_argument(
        "--notify-via-agent-mail",
        action="store_true",
        help="Send Agent Mail notification on completion",
    )
    p.add_argument("--parent-run-id", default=None, help="Parent ACP run ID")
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    p.set_defaults(func=cli_dispatch)


def _add_status_parser(subparsers) -> None:
    p = subparsers.add_parser("status", help="Get run state")
    p.add_argument("run_id", help="ACP run ID")
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    p.set_defaults(func=cli_status)


def _add_await_parser(subparsers) -> None:
    p = subparsers.add_parser("await", help="Wait for run completion")
    p.add_argument("run_id", help="ACP run ID")
    p.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Maximum wait time in seconds (default: 1800)",
    )
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    p.set_defaults(func=cli_await)


def _add_result_parser(subparsers) -> None:
    p = subparsers.add_parser("result", help="Read run result")
    p.add_argument("run_id", help="ACP run ID")
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    p.set_defaults(func=cli_result)


def _add_resolve_parser(subparsers) -> None:
    p = subparsers.add_parser(
        "resolve", help="Resolve agent or role to execution route"
    )
    p.add_argument("--agent-id", default=None, help="Explicit agent ID to resolve")
    p.add_argument("--role", default=None, help="Operational role to resolve")
    p.add_argument("--model", default=None, help="Explicit model override")
    p.add_argument("--workspace", default="home", help="Workspace (default: home)")
    p.add_argument(
        "--no-strict",
        action="store_true",
        help="Disable strict model validation",
    )
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    p.set_defaults(func=cli_resolve)


def _add_session_subparser(subparsers) -> None:
    sp = subparsers.add_parser("session", help="Persistent session management")
    sp.set_defaults(func=cli_session)
    session_sub = sp.add_subparsers(dest="session_action", required=True)

    create_p = session_sub.add_parser("create", help="Create a new persistent session")
    create_p.add_argument("--caller-agent-id", default=None)
    create_p.add_argument("--target-agent-id", required=True)
    create_p.add_argument("--requested-role", default=None)
    create_p.add_argument("--workspace", default="home")
    create_p.add_argument("--objective", default=None)
    create_p.add_argument("--model", default=None)
    create_p.add_argument("--session-name", default=None)
    create_p.add_argument("--json", action="store_true")

    show_p = session_sub.add_parser("show", help="Show session details")
    show_p.add_argument("session_id")
    show_p.add_argument("--json", action="store_true")

    continue_p = session_sub.add_parser("continue", help="Continue a session")
    continue_p.add_argument("session_id")
    continue_p.add_argument("--objective", required=True)
    continue_p.add_argument("--async", dest="is_async", action="store_true")
    continue_p.add_argument("--json", action="store_true")

    close_p = session_sub.add_parser("close", help="Close a session")
    close_p.add_argument("session_id")
    close_p.add_argument("--json", action="store_true")

    reconcile_p = session_sub.add_parser("reconcile", help="Reconcile sessions")
    reconcile_p.add_argument("--all", action="store_true")
    reconcile_p.add_argument("--json", action="store_true")


# ── Entry point ─────────────────────────────────────────────────────────────────


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
