# Playbook: Add an audit event

> When to use, prerequisites, numbered steps, a verification checklist, and a worked example.

## When to use
Use this for every state-changing service function (create/update/delete/register/login/cancel/
request_*). `make feature-check` fails if a mutation lacks `audit.record`.

## Prerequisites
- You have read [../14-audit-and-activity-logging.md](../14-audit-and-activity-logging.md).

## Steps
1. **Add the `AuditAction`** (and `AuditResource`/`AuditReason` if needed) in `app/core/constants.py`.
2. **Call `audit.record`** in the service with `before`/`after` snapshots:
   ```python
   await audit.record(
       AuditAction.NOTE_UPDATE,
       AuditResource.NOTE,
       note_id,
       before=NoteOut.model_validate(before),
       after=NoteOut.model_validate(updated),
   )
   ```
   Use `outcome=AuditOutcome.FAILURE/DENIED` and `metadata={...}` for failures.
3. **Never include secrets**: redaction masks `Redaction.FIELDS`; do not add new secret field names
   outside that set.
4. **Test** with the list sink (`audit.set_sink(ListAuditSink())`).
5. **README** Business rules (Audit events).
6. **Verify**: `make lint && make test && make feature-check`.

## Verification checklist
- [ ] `AuditAction` member added and referenced.
- [ ] `audit.record` called with before/after (or outcome/metadata).
- [ ] No secrets in metadata.
- [ ] Test asserts the entry.
- [ ] README updated.
- [ ] `make lint && make test && make feature-check` pass.

## Worked example
`notes.update` records `note.update` with a redacted `NoteOut` diff (password never present, but
the pattern is the same for `user.update`).