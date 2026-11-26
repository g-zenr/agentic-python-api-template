# Playbook: Add a background job

> When to use, prerequisites, numbered steps, a verification checklist, and a worked example.

## When to use
Use this when work is slow (> ~1s), calls an external service, or fans out over many rows. The
request must return immediately; the job runs on a worker.

## Prerequisites
- The owning feature exists; you have read [../13-background-jobs.md](../13-background-jobs.md).

## Steps
1. **Add the `JobType` member** in `app/core/constants.py` (e.g. `NOTES_EXPORT = "notes.export"`).
2. **Optional payload schema** in the feature's `schemas.py` (extend `ApiModel`) if the job takes input.
3. **Write the handler** in `app/features/<x>/jobs.py`:
   ```python
   @job_handler(JobType.NOTES_EXPORT, timeout=JobPolicy.DEFAULT_TIMEOUT)
   async def export_notes(ctx: JobContext) -> dict:
       """One-line description (idempotent, read-only)."""
       await ctx.raise_if_cancelled()
       await ctx.progress(50)
       return {"count": 3}
   ```
   Handlers MUST be idempotent, report progress, check `raise_if_cancelled`, return a small dict,
   and raise `PermanentError(Msg.X)` for non-retryable failures.
4. **Service** `request_<x>` calls `jobs_service.submit(user, JobType.X, idempotency_key=...)` and
   `audit.record(...)`.
5. **Router** returns `202` with `set_poll_headers(response, job.id)` and accepts `IdempotencyKey`.
6. **`Msg` keys** if the job surfaces new text (every locale file).
7. **Tests** using `FakeJobStore` + `execute()` (see `tests/test_jobs.py`).
8. **README** (Business rules: Jobs) + registry + CHANGELOG; then
   `make lint && make test && make feature-check`.

## Verification checklist
- [ ] `JobType` member added and referenced.
- [ ] Handler idempotent, with progress + cancel checks + small result.
- [ ] Service submits + audits; router returns 202 + poll headers + `IdempotencyKey`.
- [ ] Tests via `FakeJobStore`/`execute()`.
- [ ] README/registry/CHANGELOG updated.
- [ ] `make lint && make test && make feature-check` pass.

## Worked example
`notes.export`: `POST /notes/export` → `jobs_service.submit` → `export_notes` handler pages the
user's notes, reports progress, and returns `{count, markdown}`.