"""Notes job handlers: the reference background job (async export)."""

from app.core.constants import JobPolicy, JobType, Pagination
from app.core.jobs import JobContext, job_handler
from app.features.notes.repository import notes_repo
from app.shared.helpers.pagination import PageParams


@job_handler(JobType.NOTES_EXPORT, timeout=JobPolicy.DEFAULT_TIMEOUT)
async def export_notes(ctx: JobContext) -> dict:
    """Export the user's notes as one markdown string, page by page (idempotent, read-only)."""
    # Large outputs belong in object storage with a URL in the result (out of scope here; the
    # RESULT_MAX_BYTES guard in the worker enforces the limit).
    page, done, blocks = 1, 0, []
    total = 0
    while True:
        await ctx.raise_if_cancelled()
        items, total = await notes_repo.list_for_user(
            ctx.user_id, PageParams(page=page, size=Pagination.MAX_SIZE)
        )
        blocks.extend(f"# {note.title}\n\n{note.body}" for note in items)
        done += len(items)
        if total:
            await ctx.progress(done * 100 // total)
        if len(items) < Pagination.MAX_SIZE:
            break
        page += 1
    return {"count": done, "markdown": "\n\n---\n\n".join(blocks)}
