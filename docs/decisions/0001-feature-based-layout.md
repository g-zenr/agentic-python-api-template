# 0001 — Feature-based layout

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
Layer-by-layer (all routers together, all services together) folders make it hard to see everything
about one concept and hard for an agent to change a feature safely. We want each feature to be a
self-contained, copyable unit.

## Decision
Organize code by feature: `app/features/<x>/` contains `router.py`, `service.py`,
`repository.py`, `schemas.py`, optional `deps.py`/`tools.py`, and a `README.md`. Routers and tools
are auto-discovered. A feature may import another feature's service/repository/deps, never its
router.

## Consequences
- A feature is easy to reason about, copy (from `notes`), and remove.
- Cross-feature reuse goes through services/repositories, not routers.
- Auto-discovery keeps `main.py` stable as features come and go.