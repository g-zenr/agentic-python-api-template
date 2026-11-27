# 10 — Testing

> The DB-free test suite, what the docs/lifecycle guards enforce, and how to test a feature.

## What you will learn
- The test layout and the "no database" rule.
- What `test_docs` and `test_lifecycle` enforce.
- How to test a new feature by stubbing the repository.

## Layout
```
tests/
├── conftest.py          # sets ENV=test + dummy DATABASE_URL before any app import
├── features/            # per-feature tests: test_<feature>.py
├── integration/         # @pytest.mark.integration: real DB (run via `make test-integration`)
├── test_docs.py         # docs structure guards
├── test_lifecycle.py    # registry + workflow guards
├── test_i18n.py         # locale parity
├── test_mcp.py          # MCP tool registration
├── test_health.py       # health endpoint + error envelope + i18n
└── test_utils.py        # time/text/json utilities
```

## The no-database rule
The default suite runs **without a database**. `tests/conftest.py` sets `ENV=test` and a dummy
`DATABASE_URL` before importing the app. `httpx.ASGITransport` does not trigger the lifespan, so
`connect_db` never runs. Feature tests stub the repository rather than hitting Prisma.

## Integration suite (the one exception)
`tests/integration/` is marked `@pytest.mark.integration` and is **deselected by default**
(`addopts = -m 'not integration'`). It needs a real, migrated PostgreSQL (`DATABASE_URL` or
`TEST_DATABASE_URL`) and covers what stubs cannot: real transaction rollback, the append-only
audit trigger, keyset pagination over live rows, and raw-SQL PII scrubbing. Run it with
`make test-integration` (or `uv run pytest -m integration -o addopts=""`). Raw-SQL, trigger and
transaction changes require a test here (Definition of Done).

## What the docs/lifecycle tests enforce
- `test_docs.py`: every feature has a README with all 8 headings in order; every doc is linked
  from `docs/README.md`; every non-empty `.py` has a module docstring; `AGENTS.md`, `CLAUDE.md`,
  `README.md` exist; every feature appears in `docs/03-project-structure.md`.
- `test_lifecycle.py`: registry ↔ folder parity; Change history present; playbooks exist and are
  linked; `AGENTS.md` has "Task workflow" and "Definition of Done"; no orphan `Msg`/locale drift;
  `check_feature.py` exits 0; a full ADD→REMOVE round trip on a temp copy via `FEATURE_ROOT`.

## Testing a new feature
Test the **service** with a stubbed repository (see `tests/features/test_notes.py`). Example of the
ownership rule:

```python
async def test_get_other_users_note_raises(monkeypatch):
    # stub notes_repo.get to return a note owned by someone else
    with pytest.raises(NotFoundError):
        await service.get(user, "note-id")
```

## Run commands
- `make test` — the full suite (integration + speed deselected).
- `make test-speed` / `make test-slo` — the API **speed suite** (latency SLO `API_SLO_MS`,
  default 1000ms local; set 2000 deployed; `API_BASE_URL` targets a deployed API).
- `make test-integration` — the DB-backed `integration` suite (needs a real database).
- `make docs-check` — just the docs + lifecycle guards.
- `make lint` — ruff + `mypy` + `feature-check`.

## Quality and speed suites
- `tests/test_api_quality.py` — route metadata (summary/description on every route), the response
  envelope on success/error/404/405/422, security headers, auth-required behavior.
- `tests/test_api_speed.py` (`-m speed`) — per-request latency SLO (`API_SLO_MS`; 1000ms local /
  2000ms deployed) plus an aggregate p95 gate. NOT functional tests: they assert how fast the API
  answers, not what it returns.

## Fakes
`tests/fakes.py` provides `FakeJobStore` (in-memory `JobStore`), `ListAuditSink` and
`ListActivitySink`. Handlers are tested via `execute()` against `FakeJobStore`; audit tests
install a list sink with `audit.set_sink`. No default-run test needs Redis or Postgres.

## Common mistakes
- Requiring a live database in a default-run (non-`integration`) test.
- Testing routers instead of services.
- Adding a feature without a `tests/features/test_<x>.py`.

## See also
- [12 — Feature lifecycle](12-feature-lifecycle.md)
- [Playbook: add a feature](playbooks/add-feature.md)