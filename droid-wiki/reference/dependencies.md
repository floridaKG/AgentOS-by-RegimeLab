# Dependencies

## Overview

Agent OS is designed to be lightweight with minimal dependencies. The core system requires only Python and one LLM provider. All optional dependencies add specific capabilities without increasing the baseline requirements.

## Python dependencies

### Core (always installed)

| Package | Version | Purpose |
|---|---|---|
| `pyyaml` | >= 6.0 | YAML parsing for registry files |

Installed via: `pip install -r requirements.txt`

### Optional adapters

The following packages are not installed by default. They are required only when the corresponding external service is enabled:

| Package | Version | Required For | Purpose |
|---|---|---|---|
| `pinecone` | >= 9.0.0 | Semantic memory | Pinecone vector search client |
| `neo4j` | >= 5.20.0 | Graph memory | Neo4j knowledge graph driver |

To install optional adapters:

```bash
pip install pinecone>=9.0.0 neo4j>=5.20.0
```

Or uncomment them in `requirements.txt` and reinstall.

## External tools

### ACPx (MIT License)

The ACPx launcher provides universal agent launch, cooperative cancellation, named parallel sessions, crash reconnect, and DAG orchestration.

| Detail | Value |
|---|---|
| License | MIT |
| Installation | `npm install -g acpx` |
| Minimum | Any recent version |
| Purpose | Launching and managing AI coding agents through a unified interface |

### CodeGraph (MIT License)

CodeGraph answers structural code questions in a single query instead of chaining grep/read calls.

| Detail | Value |
|---|---|
| License | MIT |
| Installation | `npm install -g @codegraph/cli` |
| Minimum | Any recent version |
| Purpose | Code structure queries (callers, callees, impact analysis) |

## System requirements

### Required

| Requirement | Minimum Version | Notes |
|---|---|---|
| **Python** | 3.10+ | Core runtime. Check with `python3 --version` |
| **LLM provider** | Any | OpenAI, Anthropic, or OpenRouter-compatible API key |

### Optional

| Requirement | Minimum Version | Notes |
|---|---|---|
| **Git** | Any | Needed for skill updates and version control |
| **Node.js** | 18+ | Needed for ACPx and CodeGraph |
| **Obsidian** | Any | Optional desktop app for vault graph view |

### Supported platforms

| Platform | Status |
|---|---|
| Linux (Debian/Ubuntu, Fedora, Arch) | Fully supported |
| macOS (Homebrew or system Python) | Fully supported |
| WSL2 (Windows Subsystem for Linux) | Fully supported (required for Windows users) |
| Native Windows | Not supported |

## Key files

| File | Purpose |
|---|---|
| `requirements.txt` | Python dependency manifest |
| `SETUP.md` | Installation guide with platform-specific instructions |
