# Playbook: Add a message and locale

> When to use, prerequisites, numbered steps, a verification checklist, and a worked example.

## When to use
Use this whenever you add or change **user-facing text** (success messages, error messages).

## Prerequisites
- You know which feature needs the text.

## Steps
1. **Add the member.** Add a member to `Msg` in `app/core/messages.py` whose value is a dotted key
   (e.g. `NOTE_CREATED = "note.created"`).
2. **Add the key to EVERY locale.** Add the same key to every file in `app/core/locales/`
   (`en.json`, `fil.json`, …). Preserve any `{placeholder}` exactly.
3. **Use it.** Reference `Msg.X` in the service/router; never inline the text.
4. **Docs.** If it introduces a user-visible behavior, note it in the feature README Change
   history; add a CHANGELOG entry if user-facing; bump the version.
5. **Verify.** Run `make test` (i18n parity) and `make feature-check` (orphan check); then
   `make lint`.

## Verification checklist
- [ ] `Msg` member added with a dotted key.
- [ ] Key added to EVERY locale file.
- [ ] Placeholders identical across locales.
- [ ] Referenced in code (no orphan).
- [ ] CHANGELOG/version updated if user-facing.
- [ ] `make test` and `make feature-check` pass.

## Worked example
`Msg.NOTE_CREATED = "note.created"` exists in both `en.json` ("Note created") and `fil.json`
("Nagawa na ang note") and is used by `notes.router.create_note`.