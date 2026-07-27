"""Tiny env loader for cron-invoked memory scripts.

Cron inherits minimal env (PATH/HOME only). Indexers, promoters, and other
memory tooling rely on PINECONE_API_KEY and AGENT_MEMORY_NEO4J_* being set.

Import this module at the top of any script that may run from cron:
    from agent_os_memory._envload import load_env
    load_env()

Or run inline (when not packaged):
    exec(open(f"{_AOH}/memory/_envload.py").read()); load_env()

Canonical env file: $AGENT_OS_HOME/.env.agent-os
Format: shell `export KEY=value` lines or bare `KEY=value`.
"""
import os
from pathlib import Path

_AOH = os.environ.get("AGENT_OS_HOME") or os.path.dirname(os.path.abspath(__file__))

_CANONICAL = Path(f"{_AOH}/.env.agent-os")


def load_env(path: Path = _CANONICAL) -> None:
    if os.environ.get("PINECONE_API_KEY"):
        return
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)
