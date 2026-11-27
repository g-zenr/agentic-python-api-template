"""User repository: generic CRUD plus email lookup. Data access only."""

from typing import cast

from prisma.models import User

from app.shared.helpers.repository import BaseRepository


class UserRepository(BaseRepository[User]):
    async def find_by_email(self, email: str) -> User | None:
        """Look up a user by case-insensitive email."""
        return cast("User | None", await self.d.find_first(where={"email": email.lower()}))


users_repo = UserRepository("user")
