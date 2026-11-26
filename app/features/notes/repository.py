"""Note repository: generic CRUD plus a per-user listing. Data access only."""

from prisma.models import Note

from app.shared.helpers.pagination import PageParams
from app.shared.helpers.repository import BaseRepository


class NotesRepository(BaseRepository[Note]):
    async def list_for_user(self, user_id: str, params: PageParams) -> tuple[list[Note], int]:
        """Return one page of a user's notes (newest first) plus the total count."""
        return await self.paginate(params, where={"user_id": user_id})


notes_repo = NotesRepository("note")
