# Playbook: Update a feature

> When to use, prerequisites, numbered steps, a verification checklist, and a worked example.

## When to use
Use this for **any** change to an existing feature: behavior, DB schema, a breaking API change, or
a pure refactor. If the concept is new, ADD; if obsolete, REMOVE.

## Prerequisites
- Read the feature's `README.md` and its row in [../features.md](../features.md).
- Read the touch-map in [../12-feature-lifecycle.md](../12-feature-lifecycle.md).

## Steps
1. **Read first.** Open `app/features/<x>/README.md` and its registry row.
2. **Classify the change** and follow the matching touch-map column:
   (a) behavior, (b) DB schema, (c) breaking API, (d) pure refactor (no doc change beyond a
   Change history row if behavior is identical; none if only internal names changed).
3. **Edit in layer order:** `schemas.py` → `repository.py` → `service.py` → `router.py`. Never put
   logic in the router to skip a layer.
4. **(b) Schema change:** edit `prisma/schema.prisma`, run `make migrate`, and **never** edit an
   existing migration file. Destructive changes (drop/rename column) need an ADR first.
5. **(c) Breaking API change:** write an ADR (next number), mark the old endpoint
   `deprecated=True` when possible, add a CHANGELOG entry prefixed `BREAKING:`, and bump the major
   version (minor while `0.x`).
6. **Text changes.** New/changed user-facing text → `Msg` + every locale; remove keys you orphaned.
7. **Docs + version.** Update the README sections the touch-map names, add a Change history row
   (`version | date | Added/Changed/Fixed/Removed | summary`), update "Last changed" in
   `docs/features.md`, add a CHANGELOG entry, and bump the version (patch for fixes, minor for
   features).
8. **Tests + verify.** Update or add tests. Run `make lint && make test && make feature-check`.

## Verification checklist
- [ ] README + registry row read before editing.
- [ ] Change classified (behavior / schema / breaking / refactor).
- [ ] Edited in layer order (schemas → repository → service → router).
- [ ] Schema change: new migration via `make migrate` (no edits to old migrations); ADR if destructive.
- [ ] Breaking change: ADR + `deprecated=True` + `BREAKING:` CHANGELOG + major/minor bump.
- [ ] `Msg`/locale updated; orphaned keys removed.
- [ ] README sections + Change history row; "Last changed" updated; CHANGELOG entry; version bumped.
- [ ] Tests updated/added.
- [ ] `make lint && make test && make feature-check` all pass.

## Worked example
Adding a `PATCH /notes/{id}` partial update to `notes` is a behavior change: `NoteUpdate` was added
to `schemas.py`, `service.update` uses `model_dump(exclude_unset=True)`, the README Endpoints/Business
rules were edited, a Change history row was added, and "Last changed" was bumped.