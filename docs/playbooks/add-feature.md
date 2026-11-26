# Playbook: Add a feature

> When to use, prerequisites, numbered steps, a verification checklist, and a worked example.

## When to use
Use this when you need a **new** business concept that no existing feature owns. If a feature
already owns the concept, UPDATE it instead (see `update-feature.md`).

## Prerequisites
- The repo is set up: `make install`.
- You have read [../12-feature-lifecycle.md](../12-feature-lifecycle.md) and the `notes` README
  ([../../app/features/notes/README.md](../../app/features/notes/README.md)).

## Steps
1. **Pick a name.** Singular, lowercase `snake_case`, matching `^[a-z][a-z0-9_]*$`. Confirm it is
   not already in [../features.md](../features.md).
2. **Scaffold.** Run `make feature name=<x>`. This creates `app/features/<x>/` with
   `__init__.py`, `router.py`, `service.py`, `repository.py`, `schemas.py`, and a pre-filled
   `README.md`, and appends an `experimental` row to `docs/features.md`.
3. **Fill the README.** Complete `app/features/<x>/README.md`: Purpose, Endpoints, Data model,
   Business rules, Dependencies.
4. **Persistence (optional).** If the feature stores data, add the model to
   `prisma/schema.prisma`, run `make migrate`, and follow
   [add-model-and-migration.md](add-model-and-migration.md).
5. **Constants and messages.** Add the `Tag` constant, any `Limits`, and `Msg` keys (in **every**
   locale file). Follow [add-message-and-locale.md](add-message-and-locale.md).
6. **Implement in layer order:** `schemas.py` → `repository.py` → `service.py` → `router.py`
   (add `deps.py` / `tools.py` only if needed). Copy patterns from `notes`. Slow work → a job
   ([add-background-job.md](add-background-job.md)); every mutation → `audit.record`
   ([add-audit-event.md](add-audit-event.md)); hot reads → `@cached`
   ([add-cached-read.md](add-cached-read.md)).
7. **Tests.** Add `tests/features/test_<x>.py`; stub the repository so service logic is testable
   without a database.
8. **Docs + version.** Update [../03-project-structure.md](../03-project-structure.md); in
   `docs/features.md` set Status `stable` once endpoints are done and fill the Prisma/MCP columns;
   add a `docs/CHANGELOG.md` `Added` entry; bump the **minor** version in `pyproject.toml`.
9. **Verify.** Run `make lint && make test && make feature-check`.

## Verification checklist
- [ ] Name matches `^[a-z][a-z0-9_]*$` and is not already registered.
- [ ] `make feature name=<x>` ran; folder + README + Active row exist.
- [ ] README has all 8 sections filled.
- [ ] Model added + `make migrate` (if persistence).
- [ ] `Tag`/`Limits`/`Msg` added; every locale updated.
- [ ] Implemented schemas → repository → service → router.
- [ ] `tests/features/test_<x>.py` added.
- [ ] `docs/03-project-structure.md`, `docs/features.md`, `docs/CHANGELOG.md` updated.
- [ ] Minor version bumped in `pyproject.toml`.
- [ ] `make lint && make test && make feature-check` all pass.

## Worked example
The `notes` feature was built exactly this way: a `Note` model, `NotesRepository(BaseRepository)`,
a service with an ownership guard, and a fully authenticated CRUD router. See
[../../app/features/notes/README.md](../../app/features/notes/README.md).