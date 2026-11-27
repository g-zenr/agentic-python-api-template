"""Note service: business rules, ownership, audit, caching, versioning, and the export job.

Every id-scoped operation goes through `_owned` (missing and foreign notes raise the SAME error).
Mutations run in a transaction with the audit write; cache invalidation runs after commit.
"""

from typing import Any, cast

from prisma.models import Note, User

from app.core import audit
from app.core.cache import cached
from app.core.constants import (
    AuditAction,
    AuditResource,
    CacheNS,
    CacheTTL,
    JobType,
)
from app.core.exceptions import NotFoundError, PreconditionFailedError
from app.core.messages import Msg
from app.core.uow import after_commit, transaction
from app.features.jobs import service as jobs_service
from app.features.jobs.schemas import JobOut
from app.features.notes.repository import notes_repo
from app.features.notes.schemas import NoteCreate, NoteOut, NoteUpdate
from app.shared.helpers.pagination import PageParams, parse_sort


async def _owned(user: User, note_id: str) -> Note:
    """Fetch a note owned by `user` or raise NotFoundError (never leak existence)."""
    note = await notes_repo.get(note_id)
    if note is None or note.user_id != user.id:
        raise NotFoundError(Msg.NOTE_NOT_FOUND)
    return note


async def create(user: User, payload: NoteCreate) -> Note:
    """Create a note, audit it, and invalidate the user's note list after commit."""
    async with transaction():
        note = await notes_repo.create(data={**payload.model_dump(), "user_id": user.id})
        await audit.record(
            AuditAction.NOTE_CREATE, AuditResource.NOTE, note.id, after=NoteOut.model_validate(note)
        )
    await after_commit(lambda: list_notes.invalidate_scope(user.id))
    return note


@cached(
    CacheNS.NOTES,
    CacheTTL.SHORT,
    type_=tuple[list[Note], int],
    key=lambda user, params, sort=None, q=None: (params.page, params.size, sort, q),
    scope=lambda user, params, sort=None, q=None: user.id,
)
async def list_notes(
    user: User, params: PageParams, sort: str | None = None, q: str | None = None
) -> tuple[list[Note], int]:
    """List the user's notes (cached per user + page + sort + q). `q` filters titles."""
    where: dict[str, Any] = {"user_id": user.id}
    if q:
        where["title"] = {"contains": q, "mode": "insensitive"}
    order = parse_sort(sort, {"created_at", "updated_at", "title"})
    return await notes_repo.paginate(params, where=where, order=order)


async def get(user: User, note_id: str) -> Note:
    """Return one of the user's notes."""
    return await _owned(user, note_id)


async def update(user: User, note_id: str, payload: NoteUpdate, expected_version: int) -> Note:
    """Optimistically update a note (If-Match), audit the diff, invalidate the list after commit."""
    before = await _owned(user, note_id)
    async with transaction():
        ok = await notes_repo.update_versioned(
            note_id, expected_version, payload.model_dump(exclude_unset=True)
        )
        if not ok:
            raise PreconditionFailedError(Msg.PRECONDITION_FAILED)
        updated = cast("Note", await notes_repo.get(note_id))
        await audit.record(
            AuditAction.NOTE_UPDATE,
            AuditResource.NOTE,
            note_id,
            before=NoteOut.model_validate(before),
            after=NoteOut.model_validate(updated),
        )
    await after_commit(lambda: list_notes.invalidate_scope(user.id))
    return updated


async def delete(user: User, note_id: str) -> None:
    """Delete one of the user's notes, audit it, invalidate the list after commit."""
    before = await _owned(user, note_id)
    async with transaction():
        await notes_repo.delete(note_id)
        await audit.record(
            AuditAction.NOTE_DELETE,
            AuditResource.NOTE,
            note_id,
            before=NoteOut.model_validate(before),
        )
    await after_commit(lambda: list_notes.invalidate_scope(user.id))


async def request_export(user: User, idempotency_key: str | None) -> JobOut:
    """Submit a notes export job (idempotent by key) and audit the request in the same tx."""
    async with transaction():
        job = await jobs_service.submit(user, JobType.NOTES_EXPORT, idempotency_key=idempotency_key)
        await audit.record(AuditAction.NOTE_EXPORT_REQUEST, AuditResource.JOB, job.id)
    return job
