"""Auth repositories: refresh tokens (rotating families) and one-time tokens (single use)."""

from datetime import datetime
from typing import Any, cast

from prisma.models import OneTimeToken, RefreshToken

from app.shared.helpers.repository import ReadRepository
from app.shared.utils.time import utcnow


class RefreshTokenRepository(ReadRepository[RefreshToken]):
    async def find_by_hash(self, token_hash: str) -> RefreshToken | None:
        return cast(
            "RefreshToken | None", await self.d.find_unique(where={"token_hash": token_hash})
        )

    async def create(self, data: dict[str, Any]) -> RefreshToken:
        return cast("RefreshToken", await self.d.create(data=data))

    async def mark_replaced(self, token_id: str, replaced_by: str) -> None:
        """Record the replacement token hash on a consumed row (rotation chain)."""
        await self.d.update(where={"id": token_id}, data={"replaced_by": replaced_by})

    async def revoke_if_active(self, token_id: str) -> bool:
        result = await self.d.update_many(
            where={"id": token_id, "revoked_at": None},
            data={"revoked_at": utcnow()},
        )
        return cast(int, result) == 1

    async def revoke_family(self, family_id: str) -> int:
        return cast(
            int,
            await self.d.update_many(
                where={"family_id": family_id, "revoked_at": None}, data={"revoked_at": utcnow()}
            ),
        )

    async def revoke_all_for_user(self, user_id: str) -> int:
        return cast(
            int,
            await self.d.update_many(
                where={"user_id": user_id, "revoked_at": None}, data={"revoked_at": utcnow()}
            ),
        )

    async def purge(self, cutoff: datetime) -> int:
        return cast(int, await self.d.delete_many(where={"expires_at": {"lt": cutoff}}))


class OneTimeTokenRepository(ReadRepository[OneTimeToken]):
    async def find_by_hash(self, token_hash: str) -> OneTimeToken | None:
        return cast(
            "OneTimeToken | None", await self.d.find_unique(where={"token_hash": token_hash})
        )

    async def create(self, data: dict[str, Any]) -> OneTimeToken:
        return cast("OneTimeToken", await self.d.create(data=data))

    async def consume(self, token_id: str) -> bool:
        result = await self.d.update_many(
            where={"id": token_id, "used_at": None}, data={"used_at": utcnow()}
        )
        return cast(int, result) == 1

    async def invalidate_unused(self, user_id: str, purpose: str) -> int:
        return cast(
            int,
            await self.d.update_many(
                where={"user_id": user_id, "purpose": purpose, "used_at": None},
                data={"used_at": utcnow()},
            ),
        )

    async def purge(self, cutoff: datetime) -> int:
        return cast(int, await self.d.delete_many(where={"expires_at": {"lt": cutoff}}))


refresh_repo = RefreshTokenRepository("refreshtoken")
one_time_repo = OneTimeTokenRepository("onetimetoken")
