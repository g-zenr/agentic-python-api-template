"""User schemas: output model (never exposes the password hash) and update payload."""

from datetime import datetime

from pydantic import Field, field_validator

from app.core.config import settings
from app.core.constants import Limits, Role
from app.shared.schemas import ApiModel


class UserOut(ApiModel):
    id: str
    email: str
    name: str
    role: Role
    locale: str
    is_active: bool
    created_at: datetime


class UserUpdate(ApiModel):
    name: str | None = Field(default=None, max_length=Limits.NAME_MAX)
    locale: str | None = Field(default=None, description="One of the supported locale codes.")

    @field_validator("locale")
    @classmethod
    def _check_locale(cls, value: str | None) -> str | None:
        if value is not None and value not in settings.supported_locales:
            raise ValueError(f"locale must be one of {settings.supported_locales}")
        return value


class AccountErasePayload(ApiModel):
    user_id: str
