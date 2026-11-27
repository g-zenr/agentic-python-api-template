"""Shared helpers: http/etag, idempotency, pagination errors, generic repository, responses."""

from types import SimpleNamespace

import pytest

from app.core.exceptions import BadInputError, ConflictError
from app.shared.helpers import http as http_helpers
from app.shared.helpers import repository as repo_mod
from app.shared.helpers.idempotency import purge_expired, run_once
from app.shared.helpers.pagination import CursorParams, PageParams, decode_cursor, parse_sort
from app.shared.helpers.repository import BaseRepository, ReadRepository
from app.shared.helpers.responses import cursor_page_of, ok, page_of
from app.shared.schemas import ApiResponse

# --- http helpers ------------------------------------------------------------


def test_client_ip_honors_proxy_when_trusted(monkeypatch):
    monkeypatch.setattr(http_helpers.settings, "trust_proxy_headers", True)
    req = SimpleNamespace(
        client=SimpleNamespace(host="10.0.0.1"),
        headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8"},
    )
    assert http_helpers.client_ip(req) == "1.2.3.4"

    monkeypatch.setattr(http_helpers.settings, "trust_proxy_headers", False)
    assert http_helpers.client_ip(req) == "10.0.0.1"

    assert http_helpers.client_ip(SimpleNamespace(client=None, headers={})) is None


def test_etag_matches_variants():
    req = SimpleNamespace(headers={"if-none-match": '"abc", "def"'})
    assert http_helpers.etag_matches(req, '"abc"') is True
    assert http_helpers.etag_matches(req, '"zzz"') is False
    assert http_helpers.etag_matches(SimpleNamespace(headers={}), '"abc"') is False
    star = SimpleNamespace(headers={"if-none-match": "*"})
    assert http_helpers.etag_matches(star, '"abc"') is True


def test_parse_if_match_variants():
    assert http_helpers.parse_if_match('"3"') == 3
    assert http_helpers.parse_if_match('W/"7"') == 7
    assert http_helpers.parse_if_match("nope") is None
    assert http_helpers.parse_if_match(None) is None


def test_retry_and_poll_headers():
    from app.core.constants import Header

    resp = SimpleNamespace(headers={})
    http_helpers.set_retry_after(resp)
    assert resp.headers[Header.RETRY_AFTER] == "2"
    resp2 = SimpleNamespace(headers={})
    http_helpers.set_poll_headers(resp2, "job-1")
    assert resp2.headers[Header.LOCATION].endswith("/jobs/job-1")


# --- pagination --------------------------------------------------------------


def test_decode_cursor_malformed_raises():
    with pytest.raises(BadInputError):
        decode_cursor("!!!not-base64!!!")


def test_cursor_params_take():
    p = CursorParams(cursor=None, size=4)
    assert p.take == 4 and p.skip == 0


def test_parse_sort_unknown_field_raises():
    with pytest.raises(BadInputError):
        parse_sort("nope", {"created_at"})
    assert parse_sort(None, {"created_at"}) == [{"created_at": "desc"}]


# --- generic repository ------------------------------------------------------


class FakeD:
    def __init__(self):
        self.calls: list = []
        self.rows: list = []
        self.total = 0
        self.updated_row = None
        self.update_many_result = 1

    async def find_unique(self, where, **opts):
        self.calls.append(("get", where, opts))
        return self.rows[0] if self.rows else None

    async def find_many(self, **kw):
        self.calls.append(("find_many", kw))
        return self.rows

    async def count(self, where):
        return self.total

    async def create(self, data, **opts):
        self.calls.append(("create", data, opts))
        return SimpleNamespace(id="new", **data)

    async def update(self, where, data):
        self.calls.append(("update", where, data))
        return self.updated_row

    async def delete(self, where):
        self.calls.append(("delete", where))
        return self.updated_row

    async def update_many(self, where, data):
        self.calls.append(("update_many", where, data))
        return self.update_many_result


@pytest.fixture
def fake_db(monkeypatch):
    d = FakeD()
    monkeypatch.setattr(repo_mod, "current_db", lambda: SimpleNamespace(note=d))
    return d


async def test_read_repo_get_with_opts_and_paginate(fake_db):
    repo: ReadRepository = ReadRepository("note")
    d = fake_db
    d.rows = [SimpleNamespace(id="n1")]
    assert await repo.get("n1", include={"x": 1}) is not None
    assert d.calls[-1] == ("get", {"id": "n1"}, {"include": {"x": 1}})

    d.total = 5
    items, total = await repo.paginate(PageParams(page=2, size=3), where={"user_id": "u"})
    assert total == 5 and len(items) == 1
    kw = d.calls[-1][1]
    assert kw["skip"] == 3 and kw["take"] == 3  # offset pagination math


async def test_base_repository_writes_and_versioning(fake_db):
    repo: BaseRepository = BaseRepository("note")
    d = fake_db
    d.rows = [SimpleNamespace(id="n1", version=1)]
    d.updated_row = SimpleNamespace(id="n1", version=2)

    await repo.create({"title": "t"}, include={"x": 1})
    await repo.update("n1", {"title": "u"})
    await repo.delete("n1")

    d.update_many_result = 1
    assert await repo.update_versioned("n1", 1, {"title": "v2"}) is True
    where, data = d.calls[-1][1], d.calls[-1][2]
    assert where == {"id": "n1", "version": 1}
    assert data["version"] == {"increment": 1}

    d.update_many_result = 0
    assert await repo.update_versioned("n1", 99, {}) is False  # lost the race


async def test_base_repository_update_version_conflict_returns_false(fake_db):
    repo: BaseRepository = BaseRepository("note")
    fake_db.update_many_result = 0
    assert await repo.update_versioned("n1", 1, {}) is False


# --- idempotency -------------------------------------------------------------


class _IdemD:
    def __init__(self):
        self.existing = None  # what find_first returns when create is a dup
        self.record: SimpleNamespace | None = None  # the created row (normal flow)
        self.fail_create = False

    async def create(self, data):
        if self.fail_create:
            from prisma.errors import UniqueViolationError

            raise UniqueViolationError({"message": "duplicate"})
        self.record = SimpleNamespace(id="i1", status_code=None, response=None, **data)
        return self.record

    async def find_first(self, where):
        return self.existing if self.existing is not None else self.record

    async def update(self, where, data):
        for k, v in data.items():
            setattr(self.record, k, v)
        return self.record

    async def delete(self, where):
        self.record = None
        return None

    async def delete_many(self, where):
        return 3


@pytest.fixture
def idem_d(monkeypatch):
    d = _IdemD()
    monkeypatch.setattr(
        "app.shared.helpers.idempotency.current_db", lambda: SimpleNamespace(idempotencyrecord=d)
    )
    return d


async def test_run_once_first_call_executes_and_stores(idem_d):
    async def fn():
        return 201, {"id": "n1"}

    status, data, replay = await run_once("scope", "k1", {"a": 1}, fn)
    assert (status, data, replay) == (201, {"id": "n1"}, False)
    assert idem_d.record is not None and idem_d.record.status_code == 201


async def test_run_once_replay_returns_stored_response(idem_d):
    idem_d.fail_create = True
    idem_d.existing = SimpleNamespace(request_hash=None, status_code=201, response={"id": "n1"})
    from app.shared.helpers.idempotency import _hash

    idem_d.existing.request_hash = _hash({"a": 1})

    async def fn():  # pragma: no cover - must not run on a replay
        raise AssertionError("must not run")

    status, data, replay = await run_once("scope", "k1", {"a": 1}, fn)
    assert (status, data, replay) == (201, {"id": "n1"}, True)


async def test_run_once_mismatched_payload_conflicts(idem_d):
    from app.core.messages import Msg

    idem_d.fail_create = True
    idem_d.existing = SimpleNamespace(request_hash="different", status_code=201, response={})
    with pytest.raises(ConflictError) as ei:
        await run_once("scope", "k1", {"a": 1}, None)
    assert ei.value.msg == Msg.IDEMPOTENCY_MISMATCH


async def test_run_once_in_progress_conflicts(idem_d):
    from app.core.messages import Msg
    from app.shared.helpers.idempotency import _hash

    idem_d.fail_create = True
    idem_d.existing = SimpleNamespace(request_hash=_hash({"a": 1}), status_code=None, response=None)
    with pytest.raises(ConflictError) as ei:
        await run_once("scope", "k1", {"a": 1}, None)
    assert ei.value.msg == Msg.IDEMPOTENCY_IN_PROGRESS


async def test_run_once_failure_cleans_up(idem_d):
    idem_d.fn_raises = True
    idem_d.existing = SimpleNamespace(id="i1")

    async def fn():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await run_once("scope", "k1", {"a": 1}, fn)


async def test_purge_expired(idem_d, monkeypatch):
    monkeypatch.setattr("app.shared.helpers.idempotency.settings.idempotency_ttl_hours", 24)
    assert await purge_expired() == 3


# --- responses ---------------------------------------------------------------


def test_page_of_and_cursor_page_of():
    params = PageParams(page=1, size=2)
    items = [SimpleNamespace(id="a", version=1)]
    resp = page_of(items, 5, params)
    assert resp.meta.total == 5 and resp.meta.pages == 3

    cparams = CursorParams(cursor=None, size=2)
    resp2 = cursor_page_of(items, "a", cparams)
    assert resp2.cursor.has_more is True and resp2.cursor.next_cursor  # encoded

    resp3 = cursor_page_of([], None, cparams)
    assert resp3.cursor.next_cursor is None and resp3.cursor.has_more is False


def test_ok_envelope():
    resp: ApiResponse = ok({"a": 1})
    assert resp.success is True
