# Review Notes

## Current Consistency Snapshot

- Docs now reflect the dual runtime model (pipeline workers + FastAPI/React control plane).
- Cost telemetry and budget schema are documented in core spec docs.
- Deployment docs now include apply worker and Chrome CDP service surfaces.

## Residual Gaps / Follow-Up Items

1. API route integration tests are still missing for many new dashboard endpoints.
2. Frontend page-level integration tests are still deferred.
3. Human Review CSV export remains intentionally deferred.
4. Advanced filter UX beyond current status/source/stage filters remains deferred.
5. Frontend bundle-size warning still exists and may warrant route-level code splitting.

## Operational Caveats

- Apply flow remains review-first for many outcomes and does not guarantee direct submission.
- Systemd unit templates still require manual placeholder replacement before deployment.
