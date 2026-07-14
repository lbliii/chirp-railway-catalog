# Chirp Railway Catalog

The control plane for Chirp's Railway template program: template manifests,
reusable conformance checks, compatibility evidence, and support ownership.

## Conformance CLI

```bash
uv sync --frozen
uv run chirp-railway-check validate path/to/railway-template.json --repo path/to/starter
uv run chirp-railway-check local path/to/railway-template.json --repo path/to/starter
uv run chirp-railway-check smoke path/to/railway-template.json --base-url https://example.up.railway.app
uv run chirp-railway-check operations path/to/railway-template.json operations.json
```

`validate` is offline. `local` starts the manifest's production command with a
bounded generated secret and an isolated port, waits for readiness, runs the
declared stateful browser journey, and terminates the process. Checks share a
cookie jar and may extract/interpolate CSRF or other bounded values, covering
normal forms, HTMX, OOB, SSE reconnect, assets, and GET/HEAD probes. `smoke`
runs the same journey against an already-terminal live deployment and can
write a redacted JSON evidence receipt. `operations` verifies separately
captured deployment, restart, shutdown, update, rollback, and ejection proof.

Each editable Railway application lives in its own focused repository. This
catalog never becomes a monorepo containing ejectable starters.

Redacted live receipts are kept under `evidence/<template>/<source-ref>/` so a
promotion decision can be tied to the exact deployment and conformance run.

## Security

Manifests record variable names and ownership, never secret values. Evidence
contains deployment identifiers, source refs, categories, statuses, and bounded
failure text only. Failures carry the exact product surface so build/runtime,
configuration, forms, realtime, and lifecycle failures do not collapse into a
generic smoke-test error.
