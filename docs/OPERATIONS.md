# Railway catalog operations

This document is the maintainer contract for every published Chirp Railway
template. The machine-readable view is [`catalog.json`](../catalog.json); each
starter repository remains the source of truth for its code, manifest, tests,
README, changelog, and support queue.

## Ownership and support

Each catalog entry names one owner and one public support URL. New questions
belong in the starter's issue tracker so they remain searchable and ejectors
can follow the same history.

- Acknowledge a broken fresh deployment or security-sensitive report within
  two business days. Acknowledge other template questions within five.
- Label and reproduce failures against the exact template ref and Chirp
  version. Never request a secret value, database URL, or Railway token.
- Fix starter-specific behavior in the starter. Escalate a reproduced Chirp
  defect to `lbliii/chirp` with the starter issue, deployment surface, and
  redacted evidence linked in both directions.
- Set `support_health` to `degraded` when the response target is missed, a
  published deploy path is broken, or a known security/update blocker is open.
  Set it back to `healthy` only after the fix and live proof land.

Security reports that would expose credentials or an exploitable condition use
the affected repository's private GitHub security advisory. Framework-wide
reports use the Chirp repository's private advisory. Public issues may contain
sanitized follow-up only.

## Updates and compatibility

Published starters use a bounded Chirp compatibility range and a locked tested
version. Dependency updates never auto-merge into a published template.

1. Run **Chirp starter compatibility** with the proposed PEP 508 requirement,
   such as `bengal-chirp==0.10.3` or a release-candidate URL.
2. The workflow derives its matrix from every published entry in
   `catalog.json`, installs the candidate over each starter's locked
   environment, runs its test suite, and runs local production conformance.
3. Record failures by starter and product surface. Fix or explicitly defer each
   failure before recommending the Chirp update.
4. Update the starter lock, run its normal CI, publish a starter release, run a
   terminal live smoke, and update the catalog entry and evidence.
5. Set `update_status` to `blocked`, `reviewing`, or `compatible` so status is
   visible without opening Railway.

Run this sweep for every Chirp release candidate and at least monthly while a
published starter remains inside a moving compatibility range.

## Releases and evidence

Starter releases use semantic versions and update their changelog. Catalog
changes use the same policy. A promotion includes:

- a manifest validated against the catalog schema;
- green starter tests and reusable local conformance;
- a terminal live smoke tied to the deployed source ref;
- redacted deployment, restart, shutdown, update, rollback, and ejection
  receipts when those operations change;
- current marketplace copy, screenshot, demo, owner, support, and update state.

Evidence never contains secret values, connection strings, private endpoints,
customer names, or internal cost figures.

## Live-smoke cost and credential boundary

Use one disposable proof project per promotion and only the services declared
by the template. Generated template secrets and Railway reference variables are
the only credentials allowed in template configuration. Do not echo variables
or attach raw logs that could contain credentials.

Wait for terminal `SUCCESS`, `FAILED`, or `CRASHED` states; do not infer success
from a queued build. Keep the proof project only when it is the public demo or
needed for a named operations receipt. Deleting projects, repositories,
volumes, or data requires explicit maintainer authorization.

## Deprecation and retirement

Deprecation is a catalog state, not a silent deletion.

1. Set `status` to `deprecated`, explain the replacement or risk in the starter
   README and marketplace overview, and publish a final changelog entry.
2. Keep source, ejection, and support available for at least 90 days. Security
   emergencies may stop new deployments sooner but still require a notice.
3. Remove the marketplace listing only after the notice window and a recorded
   maintainer decision. Preserve the repository and catalog evidence unless a
   separate deletion is explicitly approved.
4. Set `status` to `retired` and retain the last supported ref, reason, dates,
   and successor in `catalog.json`.

The catalog is a control plane, not a monorepo: ejected application source
always remains in its focused repository.
