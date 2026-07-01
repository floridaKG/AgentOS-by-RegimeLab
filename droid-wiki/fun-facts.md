# Fun facts

## Oldest surviving code

The short-term memory backend (`memory/core/short_term.py`) at ~967 lines is the oldest and most stable component. Its SQLite + FTS5 architecture has been the foundation of the memory system since the project's earliest days. The schema (`memory/core/schema_short_term.sql`) has remained largely unchanged.

## Naming origins

Agent OS was named to emphasize that it is an operating system for agents, not a framework. The distinction is central to the project's philosophy: frameworks are libraries you import, but a harness (OS) is what agents run _on_. The name also echoes "operating system" in the traditional sense — managing resources (memory, dispatch, routing) for running programs (agents).

## TODO/FIXME count

The codebase contains scattered TODO and FIXME comments, primarily in the Python memory system files. **Hindsight** is an advanced memory extraction and fact proposal system that ships with Agent OS. It requires a Hermes + Hindsight API backend — see `memory/hindsight_bridge.py` for setup.

## The longest file

The longest source file is `scripts/skill_health.py` at ~1,700 lines, followed by `memory/core/promote.py` at ~1,067 lines and `memory/core/short_term.py` at ~967 lines.
