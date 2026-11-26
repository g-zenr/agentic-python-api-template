# Playbook: Remove a feature

> When to use, prerequisites, numbered steps, a verification checklist, and a worked example.

## When to use
Use this when a feature is obsolete and should be deleted — with or without dropping its data.
If the feature was ever released, deprecate it first (see the deprecation path).

## Prerequisites
- Read [../12-feature-lifecycle.md](../12-feature-lifecycle.md) (deprecation path, data fate).
- Run `make feature-check name=<x>` to see dependents, doc mentions, and orphaned keys.

## Steps
1. **Confirm nothing depends on it.** `make feature-check name=<x>` lists imports of
   `app.features.<x>` from other features, doc mentions, and `Msg`/constants used only by it. If
   another feature imports it, refactor that dependency FIRST (UPDATE the dependent feature).
2. **Deprecate if released.** If the feature was ever released, deprecate it first and wait one
   minor version. Skip only for features never released.
3. **Decide the data fate.** Keep the table (orphaned) or drop it. Dropping data **requires an
   ADR** (Context: why removal; Decision: drop vs keep; Consequences: irreversible loss, backup
   instruction).
4. **Run the script.** `make remove-feature name=<x> reason="..." drop_data=true|false`. This
   deletes `app/features/<x>/`, deletes `tests/features/test_<x>.py` if present, moves the registry
   row to Removed, and prints the remaining manual steps.
5. **Do the printed manual steps:** remove the Prisma model and run `make migrate` (only if
   `drop_data=true`; otherwise keep the model and note it in the ADR); delete orphaned `Msg` keys
   from `messages.py` and EVERY locale file; delete orphaned `Tag`/`Limits`/enum constants; remove
   the feature from `docs/03-project-structure.md`; remove glossary terms used only by it; fix
   remaining doc links.
6. **CHANGELOG + version.** Add the `Removed` entry and bump the minor version. The Removed
   registry row must have version, date, reason, data dropped yes/no, and an ADR link (if any).
7. **Verify.** Run `make lint && make test && make feature-check`.

Do **not** delete the feature's CHANGELOG entries or ADRs: history stays.

## Verification checklist
- [ ] `make feature-check name=<x>` shows no other feature imports it.
- [ ] Deprecated first if it was ever released.
- [ ] Data fate decided; ADR written if dropping data.
- [ ] `make remove-feature ...` ran; folder + test gone; row moved to Removed.
- [ ] Prisma model + migration handled per data fate.
- [ ] Orphaned `Msg` keys and constants removed from code + every locale.
- [ ] `docs/03-project-structure.md` and glossary updated; links fixed.
- [ ] CHANGELOG `Removed` entry + minor version bump.
- [ ] Removed row has version, date, reason, data dropped, ADR reference.
- [ ] `make lint && make test && make feature-check` all pass.

## Worked example
Removing the `notes` feature: confirm no feature imports `app.features.notes`, deprecate if it had
been released, choose `drop_data=true` (with an ADR), run
`make remove-feature name=notes reason="obsolete" drop_data=true`, then remove the `Note` model +
`Msg.NOTE_*` keys + `Tag.NOTES`, update the tree/glossary, add the `Removed` CHANGELOG entry, and
bump the version.