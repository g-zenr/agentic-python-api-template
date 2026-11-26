# 0016 — Static typing and CI gates

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
We want `mypy --strict` and CI gates (coverage, security, integration) to keep quality high.

## Decision
`mypy app` runs in CI with `strict = true` and `pydantic.mypy`; missing stubs are ignored only for
`prisma.*`, `mcp.*`, `redis.*`. Each `# type: ignore[code]` carries a same-line reason. Coverage gate
is 80%. CI runs quality (ruff, mypy, feature-check, pytest-cov), integration (Postgres+Redis,
migration drift, schemathesis), security (pip-audit, bandit, gitleaks, Trivy), and docker.

## Consequences
- Type regressions fail CI.
- A small number of justified `type: ignore`s exist at dynamic boundaries (decorators, raw SQL rows);
  the total count is tracked here and kept minimal.
- Integration tests are marked and excluded by default (`-m 'not integration'`).