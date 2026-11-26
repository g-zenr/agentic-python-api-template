# Playbook: Add a model and migration

> When to use, prerequisites, numbered steps, a verification checklist, and a worked example.

## When to use
Use this when a feature needs to persist a new entity, or when an UPDATE changes the DB schema.

## Prerequisites
- The feature exists (or you are adding one — see `add-feature.md`).
- Docker/Postgres is available, or a `DATABASE_URL` is set.

## Steps
1. **Edit the schema.** Add the `model` (and any `enum`) to `prisma/schema.prisma`. Use
   `@id @default(uuid())`, `@default(now())`, `@updatedAt`, `@@map`, and `@@index` as appropriate.
2. **Generate + migrate.** Run `make migrate` (`prisma migrate dev`). Give the migration a clear
   `--name`. **Never edit an existing migration file.**
3. **Repository.** Add/adjust the feature repository over the new delegate (`db.<model>`).
4. **Docs.** Update the README Data model section and add a Change history row; if destructive,
   write an ADR first; add a CHANGELOG `Changed` entry (note the migration name); bump the version.
5. **Tests + verify.** Adjust tests; run `make lint && make test && make feature-check`.

## Verification checklist
- [ ] Model added to `prisma/schema.prisma`.
- [ ] `make migrate` created a NEW migration (old ones untouched).
- [ ] Repository updated.
- [ ] README Data model + Change history; ADR if destructive; CHANGELOG; version bump.
- [ ] `make lint && make test && make feature-check` all pass.

## Worked example
The `Note` model was added with a `user_id` FK (`onDelete: Cascade`) and `@@index([user_id,
created_at])`; `make migrate` generated the initial migration; `NotesRepository` wraps `db.note`.