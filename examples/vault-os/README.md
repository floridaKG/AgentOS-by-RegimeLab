# Vault OS Scaffold

Vault OS is a user-owned Markdown knowledge workspace. This public scaffold
provides structure and conventions without prescribing a research domain or
shipping private domain skills.

## Suggested Structure

- `capture/` - unprocessed notes and source material
- `sources/` - normalized source records
- `insights/` - atomic notes derived from sources
- `maps/` - topic maps and indexes
- `ops/` - workflows, decisions, and maintenance records
- `registry/` - optional user-defined skills and workflows

Create a vault with:

```bash
bash $AGENT_OS_HOME/scripts/init-vault.sh --create "$HOME/my-vault"
```

Add domain skills separately. The open-source Agent OS distribution does not
bundle private investment, research, venture, or intelligence skills.
