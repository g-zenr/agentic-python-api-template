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
├── test_docs.py         # docs structure guards
├── test_lifecycle.py    # registry + workflow guards
├── test_i18n.py         # locale parity
├── test_mcp.py          # MCP tool registration
├── test_health.py       # health endpoint + error envelope + i18n
└── test_utils.py        # time/text/json utilities
```

## The no-database rule
The entire suite runs **without a database**. `tests/conftest.py` sets `ENV=test` and a dummy
`DATABASE_URL` before importing the app. `httpx.ASGITransport` does not trigger the lifespan, so
`connect_db` never runs. Feature tests stub the repository rather than hitting Prisma.

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
- `make test` — the full suite.
- `make docs-check` — just the docs + lifecycle guards.
- `make lint` — ruff + `feature-check`.

## Fakes
`tests/fakes.py` provides `FakeJobStore` (in-memory `JobStore`), `ListAuditSink` and
`ListActivitySink`. Handlers are tested via `execute()` against `FakeJobStore`; audit tests
install a list sink with `audit.set_sink`. No test needs Redis or Postgres.

## Common mistakes
- Requiring a live database in a test.
- Testing routers instead of services.
- Adding a feature without a `tests/features/test_<x>.py`.

## See also
- [12 — Feature lifecycle](12-feature-lifecycle.md)
- [Playbook: add a feature](playbooks/add-feature.md)