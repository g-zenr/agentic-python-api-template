"""Audit tests: diff/redact, entry construction, actor rules, fail-open/closed, append-only type."""

import pytest

from app.core import audit
from app.core.audit.repository import audit_repo
from app.core.config import settings
from app.core.constants import ActorType, AuditAction, AuditOutcome, AuditResource
from app.core.context import RequestContext, request_ctx
from app.shared.utils.diff import diff, redact


def test_diff_create_update_delete_and_redaction():
    created = diff(None, {"a": 1, "password": "secret"})
    assert created["a"] == {"from": None, "to": 1}
    assert created["password"] == {"from": "***", "to": "***"}

    updated = diff({"a": 1, "updated_at": "x"}, {"a": 2, "updated_at": "y"})
    assert "updated_at" not in updated
    assert updated["a"] == {"from": 1, "to": 2}

    deleted = diff({"a": 1}, None)
    assert deleted["a"] == {"from": 1, "to": None}


def test_redact_nested():
    out = redact({"outer": {"token": "t", "keep": 1}})
    assert out["outer"]["token"] == "***"
    assert out["outer"]["keep"] == 1


async def test_record_builds_entry_from_context(audit_sink):
    request_ctx.set(RequestContext(request_id="r1", ip="1.2.3.4", user_agent="ua", user_id="u1"))
    await audit.record(AuditAction.NOTE_CREATE, AuditResource.NOTE, "n1", after={"title": "t"})
    entry = audit_sink.entries[0]
    assert entry["actor_id"] == "u1"
    assert entry["actor_type"] == ActorType.USER.value
    assert entry["request_id"] == "r1"
    assert entry["ip"] == "1.2.3.4"
    assert entry["action"] == "note.create"
    assert entry["changes"]["title"] == {"from": None, "to": "t"}


async def test_actor_type_system_and_anonymous(audit_sink):
    request_ctx.set(RequestContext(actor_type=ActorType.SYSTEM))
    await audit.record(AuditAction.RETENTION_PURGE, AuditResource.LOG)
    assert audit_sink.entries[0]["actor_type"] == ActorType.SYSTEM.value

    request_ctx.set(RequestContext())
    await audit.record(
        AuditAction.AUTH_LOGIN_FAILED, AuditResource.USER, outcome=AuditOutcome.FAILURE
    )
    assert audit_sink.entries[1]["actor_type"] == ActorType.ANONYMOUS.value
    assert audit_sink.entries[1]["outcome"] == AuditOutcome.FAILURE.value


async def test_job_id_added_to_metadata(audit_sink):
    request_ctx.set(RequestContext(job_id="j1"))
    await audit.record(AuditAction.JOB_CANCEL, AuditResource.JOB, "j1", metadata={"a": 1})
    assert audit_sink.entries[0]["metadata"] == {"a": 1, "job_id": "j1"}


async def test_fail_open_logs_and_continues():
    class Boom:
        async def append(self, entry):
            raise RuntimeError("db down")

    audit.set_sink(Boom())
    try:
        await audit.record(AuditAction.NOTE_CREATE, AuditResource.NOTE, "n1")  # must not raise
    finally:
        audit.set_sink(audit_repo)


async def test_fail_closed_raises(monkeypatch):
    class Boom:
        async def append(self, entry):
            raise RuntimeError("db down")

    monkeypatch.setattr(settings, "audit_fail_closed", True)
    audit.set_sink(Boom())
    try:
        with pytest.raises(RuntimeError):
            await audit.record(AuditAction.NOTE_CREATE, AuditResource.NOTE, "n1")
    finally:
        audit.set_sink(audit_repo)


def test_repository_is_append_only_by_type():
    assert not hasattr(audit_repo, "update")
    assert not hasattr(audit_repo, "delete")
    assert hasattr(audit_repo, "append")
    assert hasattr(audit_repo, "purge_before")
