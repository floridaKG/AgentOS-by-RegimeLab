# Registry

Purpose: structured project metadata for your project.

The registry holds machine-readable and human-readable project facts:
features, infrastructure, data sources, and configuration.

## Files

Add YAML or Markdown files here to capture:

- `features.yaml` — feature catalog with status and owners
- `infra.yaml` — infrastructure and deployment targets
- `data-sources.yaml` — upstream data and APIs

## Conventions

- Keep registry files as structured YAML where possible.
- Update registry when infrastructure or features change.
- Reference registry files from governance policies when needed.
