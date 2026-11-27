"""Auth schemas: registration, login, token responses, and account-lifecycle payloads."""

from typing import Annotated

from pydantic import EmailStr, Field

from app.core.constants import Limits, TokenPurpose
from app.shared.schemas import ApiModel


PublicEmail = Annotated[
    EmailStr,
    Field(json_schema_extra={"pattern": r"(?i)^(?!.*\.(?:test|invalid|localhost|local|example)$).+$"}),
]


class RegisterIn(ApiModel):
    email: PublicEmail
    password: str = Field(min_length=Limits.PASSWORD_MIN, max_length=Limits.PASSWORD_MAX)
    name: str = Field(min_length=1, max_length=Limits.NAME_MAX)


class LoginIn(ApiModel):
    email: PublicEmail
    password: str


class TokenOut(ApiModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshIn(ApiModel):
    refresh_token: str


class LogoutIn(ApiModel):
    refresh_token: str


class VerifyEmailIn(ApiModel):
    token: str


class ChangePasswordIn(ApiModel):
    current_password: str
    new_password: str = Field(min_length=Limits.PASSWORD_MIN, max_length=Limits.PASSWORD_MAX)


class ForgotPasswordIn(ApiModel):
    email: PublicEmail


class ResetPasswordIn(ApiModel):
    token: str
    new_password: str = Field(min_length=Limits.PASSWORD_MIN, max_length=Limits.PASSWORD_MAX)


class SendTokenEmailPayload(ApiModel):
    user_id: str
    purpose: TokenPurpose
