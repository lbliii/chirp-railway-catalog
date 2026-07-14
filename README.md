# Chirp Railway Catalog

The control plane for Chirp's Railway template program: template manifests,
reusable conformance checks, compatibility evidence, and support ownership.

## Conformance CLI

```bash
uv sync --frozen
uv run chirp-railway-check validate path/to/railway-template.json --repo path/to/starter
uv run chirp-railway-check local path/to/railway-template.json --repo path/to/starter
uv run chirp-railway-check smoke path/to/railway-template.json --base-url https://example.up.railway.app
```

`validate` is offline. `local` starts the manifest's production command with a
bounded generated secret and an isolated port, waits for readiness, runs the
declared HTTP/HTMX/OOB/SSE checks, and terminates the process. `smoke` runs the
same checks against an already-terminal live deployment and can write a
redacted JSON evidence receipt.

Each editable Railway application lives in its own focused repository. This
catalog never becomes a monorepo containing ejectable starters.

## Security

Manifests record variable names and ownership, never secret values. Evidence
contains deployment identifiers, source refs, categories, statuses, and bounded
failure text only.
