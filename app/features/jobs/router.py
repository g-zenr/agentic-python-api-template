"""Jobs feature: a thin HTTP surface over the core job engine (poll/cancel; submit is elsewhere)."""

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.constants import TERMINAL_JOB_STATUSES, CacheControl, Header, JobStatus, Tag
from app.features.auth.deps import CurrentUser
from app.features.jobs import service
from app.features.jobs.schemas import JobOut
from app.shared.helpers.http import etag_for, etag_matches, set_retry_after
from app.shared.helpers.pagination import PageParams
from app.shared.helpers.responses import ok, page_of
from app.shared.schemas import ApiResponse

router = APIRouter(prefix="/jobs", tags=[Tag.JOBS])


@router.get(
    "",
    response_model=ApiResponse[list[JobOut]],
    summary="List my jobs",
    description="Paginated list of the user's jobs, newest first. Filter by `status`.",
)
async def list_jobs(
    user: CurrentUser,
    response: Response,
    params: PageParams = Depends(),
    status: JobStatus | None = Query(default=None),
) -> ApiResponse[Any]:
    if response is not None:
        response.headers[Header.CACHE_CONTROL] = CacheControl.NO_STORE
    items, total = await service.list_jobs(user, params, status)
    data = [service.to_out(i) for i in items]
    return page_of(data, total, params)


@router.get(
    "/{job_id}",
    response_model=ApiResponse[JobOut],
    summary="Poll a job",
    description="Poll until `status` is SUCCEEDED, FAILED or CANCELLED. Honor `Retry-After`. "
    "Send `If-None-Match` with the last `ETag`; 304 means nothing changed.",
)
async def get_job(
    job_id: str, request: Request, response: Response, user: CurrentUser
) -> ApiResponse[Any] | Response:
    job = await service.get(user, job_id)
    etag = etag_for(job.id, job.status, job.progress, job.updated_at)
    headers = {Header.ETAG: etag, Header.CACHE_CONTROL: CacheControl.NO_STORE}
    if etag_matches(request, etag):
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    if job.status not in TERMINAL_JOB_STATUSES:
        set_retry_after(response)
    return ok(job)


@router.post(
    "/{job_id}/cancel",
    response_model=ApiResponse[JobOut],
    summary="Cancel a job",
    description="Cancel a QUEUED job, or request cancellation of a RUNNING job. "
    "Terminal jobs cannot be cancelled.",
)
async def cancel_job(job_id: str, user: CurrentUser, response: Response) -> ApiResponse[Any]:
    response.headers[Header.CACHE_CONTROL] = CacheControl.NO_STORE
    job, msg = await service.cancel(user, job_id)
    return ok(job, msg)
