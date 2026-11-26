"""Note router: the reference for an authenticated, ownership-scoped, versioned CRUD feature.

Every route requires `VerifiedUser`. A user only ever touches their own notes. Mutations are
audited and transactional; updates use optimistic concurrency (`If-Match`); creates accept an
`Idempotency-Key`. Responses carry an `ETag` of the note version.
"""

from fastapi import APIRouter, Depends, Response, status

from app.core.constants import Header, Tag
from app.core.exceptions import PreconditionRequiredError
from app.core.messages import Msg
from app.features.auth.deps import VerifiedUser
from app.features.jobs.schemas import JobOut
from app.features.notes import service
from app.features.notes.schemas import NoteCreate, NoteOut, NoteUpdate
from app.shared.helpers.http import IdempotencyKey, IfMatch, parse_if_match, set_poll_headers
from app.shared.helpers.idempotency import IDEMPOTENCY_REPLAY, run_once
from app.shared.helpers.pagination import PageParams
from app.shared.helpers.responses import ok, page_of
from app.shared.schemas import ApiResponse

router = APIRouter(prefix="/notes", tags=[Tag.NOTES])


def _etag(version: int) -> str:
    return f'"{version}"'


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[NoteOut],
    summary="Create a note",
    description="Create a note owned by the caller. Send Idempotency-Key to make it safe to retry.",
)
async def create_note(
    response: Response, user: VerifiedUser, payload: NoteCreate, key: IdempotencyKey = None
) -> ApiResponse:
    if key:
        status_code, data, replay = await run_once(
            user.id,
            key,
            payload.model_dump(),
            lambda: _create(user, payload),
        )
        response.status_code = status_code
        if replay:
            response.headers[IDEMPOTENCY_REPLAY] = "true"
        return ok(data)
    note = await service.create(user, payload)
    response.headers[Header.ETAG] = _etag(note.version)
    return ok(NoteOut.model_validate(note), Msg.NOTE_CREATED)


async def _create(user, payload) -> tuple[int, dict]:
    note = await service.create(user, payload)
    return 201, NoteOut.model_validate(note).model_dump(mode="json")


@router.get(
    "",
    response_model=ApiResponse[list[NoteOut]],
    summary="List my notes",
    description="Paginated list of my notes. Supports ?sort= and ?q= (title search).",
)
async def list_notes(
    user: VerifiedUser,
    params: PageParams = Depends(),
    sort: str | None = None,
    q: str | None = None,
) -> ApiResponse:
    items, total = await service.list_notes(user, params, sort, q)
    return page_of(items, total, params, schema=NoteOut)


@router.post(
    "/export",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[JobOut],
    summary="Export all my notes (async)",
    description="Returns 202 immediately. Poll the URL in the Location header.",
)
async def export_notes(
    response: Response, user: VerifiedUser, key: IdempotencyKey = None
) -> ApiResponse:  # noqa: E501
    job = await service.request_export(user, key)
    set_poll_headers(response, job.id)
    return ok(job, Msg.JOB_QUEUED)


@router.get(
    "/{note_id}",
    response_model=ApiResponse[NoteOut],
    summary="Get a note",
    description="Return one of my notes by id.",
)
async def get_note(response: Response, user: VerifiedUser, note_id: str) -> ApiResponse:
    note = await service.get(user, note_id)
    response.headers[Header.ETAG] = _etag(note.version)
    return ok(NoteOut.model_validate(note))


@router.patch(
    "/{note_id}",
    response_model=ApiResponse[NoteOut],
    summary="Update a note",
    description="Partially update one of my notes. Requires If-Match with the current version.",
)
async def update_note(
    response: Response,
    user: VerifiedUser,
    note_id: str,
    payload: NoteUpdate,
    if_match: IfMatch = None,  # noqa: E501
) -> ApiResponse:
    expected = parse_if_match(if_match)
    if expected is None:
        raise PreconditionRequiredError(Msg.PRECONDITION_REQUIRED)
    note = await service.update(user, note_id, payload, expected)
    response.headers[Header.ETAG] = _etag(note.version)
    return ok(NoteOut.model_validate(note), Msg.NOTE_UPDATED)


@router.delete(
    "/{note_id}",
    response_model=ApiResponse[dict],
    summary="Delete a note",
    description="Delete one of my notes.",
)
async def delete_note(user: VerifiedUser, note_id: str) -> ApiResponse:
    await service.delete(user, note_id)
    return ok({"id": note_id}, Msg.DELETED)
