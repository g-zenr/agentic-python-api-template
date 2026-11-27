"""Keyset cursor pagination: pages must never overlap, repeat, or skip (see paginate_cursor)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.exceptions import BadInputError
from app.shared.helpers.pagination import CursorParams, encode_cursor
from app.shared.helpers.repository import ReadRepository

ORDER = [{"occurred_at": "desc"}, {"id": "desc"}]


def _row(rid: str, occurred_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(id=rid, occurred_at=occurred_at)


class FakeD:
    """Captures find_many kwargs; find_unique resolves a row by id."""

    def __init__(self, rows: list[SimpleNamespace], find_many_return: list | None = None):
        self.rows = rows
        self.find_many_return = find_many_return
        self.find_many_kwargs: dict | None = None

    async def find_unique(self, where: dict):
        for r in self.rows:
            if r.id == where["id"]:
                return r
        return None

    async def find_many(self, **kwargs):
        self.find_many_kwargs = kwargs
        if self.find_many_return is not None:
            return list(self.find_many_return)
        return list(self.rows)


def _repo(monkeypatch, fake: FakeD) -> ReadRepository:
    repo: ReadRepository = ReadRepository("x")
    monkeypatch.setattr("app.shared.helpers.repository.current_db", lambda: SimpleNamespace(x=fake))
    return repo


def _params(size: int, cursor: str | None = None) -> CursorParams:
    return CursorParams(cursor=cursor, size=size)


_T3 = datetime(2026, 1, 3, tzinfo=UTC)
_T2 = datetime(2026, 1, 2, tzinfo=UTC)
_T1 = datetime(2026, 1, 1, tzinfo=UTC)


async def test_first_page_has_no_keyset(monkeypatch):
    fake = FakeD([_row("id3", _T3)])
    repo = _repo(monkeypatch, fake)
    await repo.paginate_cursor(_params(size=2), order=ORDER)
    kw = fake.find_many_kwargs
    assert kw is not None
    assert kw["where"] == {}  # no cursor => unmodified filter
    assert kw["skip"] == 0
    assert kw["take"] == 3  # size + 1
    assert kw["order"] == ORDER


async def test_cursor_emits_keyset_and_resets_skip(monkeypatch):
    fake = FakeD([_row("id3", _T3), _row("id2", _T2), _row("id1", _T1)])
    repo = _repo(monkeypatch, fake)
    await repo.paginate_cursor(_params(size=1, cursor=encode_cursor("id3")), order=ORDER)
    kw = fake.find_many_kwargs
    assert kw is not None
    assert kw["skip"] == 0  # keyset, not offset
    assert kw["take"] == 2
    or_clauses = kw["where"]["OR"] if "OR" in kw["where"] else kw["where"]["AND"][1]["OR"]
    # occurred_at DESC => strictly older; tie-break on id DESC => strictly smaller id
    assert {"occurred_at": {"lt": _T3}} in or_clauses
    assert {"occurred_at": {"equals": _T3}, "id": {"lt": "id3"}} in or_clauses


async def test_cursor_ascending_uses_gt(monkeypatch):
    order = [{"occurred_at": "asc"}, {"id": "asc"}]
    fake = FakeD([_row("id1", _T1)])
    repo = _repo(monkeypatch, fake)
    await repo.paginate_cursor(_params(size=1, cursor=encode_cursor("id1")), order=order)
    kw = fake.find_many_kwargs
    assert kw is not None
    or_clauses = kw["where"]["OR"]
    assert {"occurred_at": {"gt": _T1}} in or_clauses
    assert {"occurred_at": {"equals": _T1}, "id": {"gt": "id1"}} in or_clauses


async def test_base_where_is_and_combined_with_keyset(monkeypatch):
    fake = FakeD([_row("id3", _T3)])
    repo = _repo(monkeypatch, fake)
    base = {"actor_id": "u1"}
    await repo.paginate_cursor(
        _params(size=1, cursor=encode_cursor("id3")), where=base, order=ORDER
    )
    kw = fake.find_many_kwargs
    assert kw is not None
    and_parts = kw["where"]["AND"]
    assert {"actor_id": "u1"} in and_parts  # caller filter preserved
    assert any("OR" in part for part in and_parts)  # keyset ANDed in


async def test_has_more_and_next_cursor(monkeypatch):
    # size+1 rows returned => has_more; next_cursor = last returned row id
    rows = [_row("a", _T3), _row("b", _T2)]
    fake = FakeD(rows, find_many_return=rows)
    repo = _repo(monkeypatch, fake)
    items, next_cursor = await repo.paginate_cursor(_params(size=1), order=ORDER)
    assert len(items) == 1
    assert next_cursor == "a"


async def test_no_more_pages_next_cursor_none(monkeypatch):
    rows = [_row("a", _T3)]
    fake = FakeD(rows, find_many_return=rows)
    repo = _repo(monkeypatch, fake)
    items, next_cursor = await repo.paginate_cursor(_params(size=5), order=ORDER)
    assert len(items) == 1
    assert next_cursor is None


async def test_unknown_cursor_raises(monkeypatch):
    fake = FakeD([_row("id3", _T3)])  # no row with id "nope"
    repo = _repo(monkeypatch, fake)
    with pytest.raises(BadInputError):
        await repo.paginate_cursor(_params(size=1, cursor=encode_cursor("nope")), order=ORDER)


async def test_no_overlap_across_pages_keyset(monkeypatch):
    """A real keyset filter over a sorted dataset yields disjoint, ordered pages."""
    data = [_row(f"id{n}", datetime(2026, 1, n, tzinfo=UTC)) for n in range(1, 6)]

    class KeysetD(FakeD):
        async def find_many(self, **kwargs):
            self.find_many_kwargs = kwargs
            # emulate DB ordering (occurred_at desc, id desc)
            ordered = sorted(data, key=lambda r: (r.occurred_at, r.id), reverse=True)
            where = kwargs.get("where") or {}
            or_clauses = where.get("OR")
            if not or_clauses and "AND" in where:
                or_clauses = where["AND"][1].get("OR")
            if or_clauses:

                def after(r):
                    for c in or_clauses:
                        ok = True
                        for k, v in c.items():
                            if "equals" in v and getattr(r, k) != v["equals"]:
                                ok = False
                            if "lt" in v and not (getattr(r, k) < v["lt"]):
                                ok = False
                            if "gt" in v and not (getattr(r, k) > v["gt"]):
                                ok = False
                        if ok:
                            return True
                    return False

                ordered = [r for r in ordered if after(r)]
            return ordered[: kwargs["take"]]

    fake = KeysetD(data)
    repo = _repo(monkeypatch, fake)
    size = 2

    page1, cur1 = await repo.paginate_cursor(_params(size=size), order=ORDER)
    ids1 = [r.id for r in page1]
    assert ids1 == ["id5", "id4"]
    assert cur1 == "id4"

    page2, cur2 = await repo.paginate_cursor(
        _params(size=size, cursor=encode_cursor(cur1)), order=ORDER
    )
    ids2 = [r.id for r in page2]
    assert ids2 == ["id3", "id2"]
    assert cur2 == "id2"

    page3, cur3 = await repo.paginate_cursor(
        _params(size=size, cursor=encode_cursor(cur2)), order=ORDER
    )
    ids3 = [r.id for r in page3]
    assert ids3 == ["id1"]
    assert cur3 is None

    seen = ids1 + ids2 + ids3
    assert len(seen) == len(set(seen)) == 5  # no duplicates, nothing skipped
