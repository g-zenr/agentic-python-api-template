# 01 — Overview

> What this template is, who it is for, and how to run it in ten lines.

## What you will learn
- What the Agentic API template provides.
- Who it is designed for (humans and AI coding agents).
- The stack and the "agentic coding" philosophy.
- A ten-line quickstart.

## What this template is
Agentic API is a production-ready **FastAPI + Prisma + PostgreSQL** starter organized by
**feature**. Each feature is a self-contained folder with its own router, service, repository,
schemas, and README. The framework wires everything together by **auto-discovery**, so adding a
feature never means editing `main.py`.

It is "batteries included" for the things every real API needs — configuration, localization,
structured errors, authentication, pagination, an MCP server — while staying small enough to read
in an afternoon.

## Who it is for
- **Backend engineers** who want a consistent, well-documented starting point.
- **AI coding agents** (OpenCode, Claude Code, and friends) that must add, update, or remove
  features correctly without asking questions. The docs and the test suite are the guardrails:
  every convention is written down, and the tests fail if a step is skipped.

## The stack
Python 3.12 · FastAPI · Uvicorn · Pydantic v2 + pydantic-settings · Prisma Client Python
(asyncio, PostgreSQL) · the official `mcp` SDK (FastMCP, optional) · PyJWT · pwdlib[argon2] ·
orjson · Redis (cache) · pytest + pytest-asyncio + httpx · ruff · Docker + docker-compose.
A standalone **worker** process (`python -m app.worker`) runs background jobs; an embedded
worker runs in-process for local dev.

## The agentic coding philosophy
AI agents are **first-class contributors**. That has three consequences, all enforced here:

1. **Documentation is a deliverable**, equal to code. Every module has a docstring, every route
   has a summary and description, every feature has a README, and the whole system has this book.
2. **Workflow is a deliverable.** ADD, UPDATE, and REMOVE each have a playbook, a docs touch-map,
   scripts for the mechanical parts, and tests that fail when a step is skipped.
3. **Conventions are enforced by tests**, not by memory. `tests/test_docs.py` and
   `tests/test_lifecycle.py` keep the docs and the registry honest.

## Quickstart
```bash
cp .env.example .env
docker compose up -d db
make install
make migrate
make dev
```
Then open `http://localhost:8000/docs`.

## Common mistakes
- Editing `main.py` to add a feature (don't — routers are auto-discovered).
- Putting user-facing text inline instead of in `Msg` + locale JSON.
- Skipping the feature README or registry row (tests will fail).

## See also
- [02 — Architecture](02-architecture.md)
- [03 — Project structure](03-project-structure.md)
- [Feature registry](features.md)