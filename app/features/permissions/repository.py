"""Permission grant repository: raw SQL over `permission_grants` (PrismaJobStore pattern).

Raw SQL keeps the store independent of the generated client (the table is administered through
the same engine that reads it in `core/authz.py`) and lets upsert/delete-many run in one
transaction via `current_db()`.
"""

from typing import Any, cast

from app.core.uow import current_db

_COLUMNS = (
    "id, user_id, resource, action, effect::text AS effect, conditions, granted_by, "
    "expires_at, created_at"
)


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    conditions = row.get("conditions")
    if isinstance(conditions, str):
        import json

        try:
            conditions = json.loads(conditions)
        except (ValueError, TypeError):
            conditions = None
    row["conditions"] = conditions
    return row


class PermissionGrantRepository:
    # B608 suppressed at the call sites below: the only interpolated fragments are the module-level
    # _COLUMNS constant and $n placeholder tokens; every value is a bound parameter.
    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        rows = await current_db().query_raw(
            f"SELECT {_COLUMNS} FROM permission_grants WHERE user_id = $1 ORDER BY resource, action;",  # noqa: E501 # nosec B608
            user_id,
        )
        return [_decode(r) for r in rows]

    async def get(self, grant_id: str) -> dict[str, Any] | None:
        sql = f"SELECT {_COLUMNS} FROM permission_grants WHERE id = $1;"  # noqa: E501 # nosec B608
        rows = await current_db().query_raw(sql, grant_id)
        return _decode(rows[0]) if rows else None

    async def replace_for_user(
        self,
        user_id: str,
        grants: list[dict[str, Any]],
        *,
        granted_by: str | None,
    ) -> list[dict[str, Any]]:
        """Delete the user's grants and insert the new set; caller wraps in a transaction."""
        client = current_db()
        await client.execute_raw("DELETE FROM permission_grants WHERE user_id = $1;", user_id)
        out: list[dict[str, Any]] = []
        for grant in grants:
            import json

            conditions = grant.get("conditions")
            rows = await client.query_raw(
                "INSERT INTO permission_grants "
                "(id, user_id, resource, action, effect, conditions, granted_by, expires_at, "
                " created_at, updated_at) "
                'VALUES (gen_random_uuid(), $1, $2, $3, $4::"GrantEffect", $5::jsonb, $6, $7, '
                "now(), now()) "
                "RETURNING " + _COLUMNS + ";",  # noqa: E501 # nosec B608
                user_id,
                grant["resource"],
                grant["action"],
                grant["effect"],
                json.dumps(conditions) if conditions is not None else None,
                granted_by,
                grant.get("expires_at"),
            )
            out.append(_decode(rows[0]))
        return out

    async def delete(self, grant_id: str) -> bool:
        result = await current_db().execute_raw(
            "DELETE FROM permission_grants WHERE id = $1;", grant_id
        )
        return cast(int, result) == 1

    async def purge_expired(self) -> int:
        return cast(
            int,
            await current_db().execute_raw(
                "DELETE FROM permission_grants WHERE expires_at IS NOT NULL AND expires_at < now();"
            ),
        )


permission_grant_repo = PermissionGrantRepository()
