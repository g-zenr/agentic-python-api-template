# 0000 — Template

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
We need a production-ready FastAPI + Prisma + PostgreSQL starter that AI coding agents can extend
correctly without asking questions. The template must be self-documenting, enforce a feature
lifecycle, and stay small enough to read in an afternoon.

## Decision
Adopt a feature-based layout with strict layering (router → service → repository → Prisma),
auto-discovery of routers/tools, centralized config/constants/messages with locale JSON, a uniform
`ApiResponse` envelope, and a documented ADD/UPDATE/REMOVE workflow enforced by tests. MCP support
is optional and removable.

## Consequences
- Adding a feature never edits `main.py`.
- Documentation and workflow are first-class, tested deliverables.
- The conventions are enforced by `tests/test_docs.py` and `tests/test_lifecycle.py`.
- Some upfront structure (shared helpers, core modules) exists before the first feature.