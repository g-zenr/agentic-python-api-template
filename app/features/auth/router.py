"""Auth router: registration, login, token rotation, logout, and account-recovery endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.core.constants import RateBucket, Tag
from app.core.messages import Msg
from app.core.ratelimit import by_ip
from app.features.auth import service
from app.features.auth.deps import CurrentUser
from app.features.auth.schemas import (
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    LogoutIn,
    RefreshIn,
    RegisterIn,
    ResetPasswordIn,
    TokenOut,
    VerifyEmailIn,
)
from app.shared.helpers.responses import ok
from app.shared.schemas import ApiResponse

router = APIRouter(prefix="/auth", tags=[Tag.AUTH])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TokenOut],
    summary="Register",
    description="Create an account and return an access + refresh token pair.",
    dependencies=[Depends(by_ip(RateBucket.REGISTER_IP))],
)
async def register(payload: RegisterIn) -> ApiResponse[Any]:
    return ok(await service.register(payload), Msg.AUTH_REGISTERED)


@router.post(
    "/login",
    response_model=ApiResponse[TokenOut],
    summary="Login",
    description="Exchange email + password for an access + refresh token pair.",
    dependencies=[Depends(by_ip(RateBucket.LOGIN_IP))],
)
async def login(payload: LoginIn) -> ApiResponse[Any]:
    return ok(await service.login(payload), Msg.AUTH_LOGGED_IN)


@router.post(
    "/refresh",
    response_model=ApiResponse[TokenOut],
    summary="Refresh",
    description="Rotate the refresh token and return a new pair. Reuse of an old token revokes the family.",  # noqa: E501
    dependencies=[Depends(by_ip(RateBucket.REFRESH_IP))],
)
async def refresh(payload: RefreshIn) -> ApiResponse[Any]:
    return ok(await service.refresh(payload.refresh_token), Msg.AUTH_LOGGED_IN)


@router.post(
    "/logout",
    response_model=ApiResponse[dict[str, Any]],
    summary="Logout",
    description="Revoke the refresh token's family. Idempotent.",
    dependencies=[Depends(by_ip(RateBucket.REFRESH_IP))],
)
async def logout(payload: LogoutIn) -> ApiResponse[Any]:
    await service.logout(payload.refresh_token)
    return ok(None, Msg.AUTH_LOGGED_OUT)


@router.post(
    "/logout-all",
    response_model=ApiResponse[dict[str, Any]],
    summary="Logout everywhere",
    description="Bump token_version and revoke all refresh tokens (invalidates all access tokens).",
    dependencies=[Depends(by_ip(RateBucket.REFRESH_IP))],
)
async def logout_all(user: CurrentUser) -> ApiResponse[Any]:
    await service.logout_all(user)
    return ok(None, Msg.AUTH_LOGGED_OUT)


@router.post(
    "/change-password",
    response_model=ApiResponse[dict[str, Any]],
    summary="Change password",
    description="Verify the current password, set a new one, and log out everywhere.",
    dependencies=[Depends(by_ip(RateBucket.LOGIN_IP))],
)
async def change_password(user: CurrentUser, payload: ChangePasswordIn) -> ApiResponse[Any]:
    await service.change_password(user, payload)
    return ok(None, Msg.AUTH_PASSWORD_CHANGED)


@router.post(
    "/verify-email",
    response_model=ApiResponse[dict[str, Any]],
    summary="Verify email",
    description="Consume a verification token and mark the email verified.",
    dependencies=[Depends(by_ip(RateBucket.REFRESH_IP))],
)
async def verify_email(payload: VerifyEmailIn) -> ApiResponse[Any]:
    await service.verify_email(payload.token)
    return ok(None, Msg.AUTH_EMAIL_VERIFIED)


@router.post(
    "/resend-verification",
    response_model=ApiResponse[dict[str, Any]],
    summary="Resend verification email",
    description="Queue another verification email for the current user.",
)
async def resend_verification(user: CurrentUser) -> ApiResponse[Any]:
    await service.resend_verification(user)
    return ok(None, Msg.AUTH_VERIFICATION_SENT)


@router.post(
    "/forgot-password",
    response_model=ApiResponse[dict[str, Any]],
    summary="Forgot password",
    description="Always the same response; emails a reset link only if the account exists.",
    dependencies=[Depends(by_ip(RateBucket.FORGOT_IP))],
)
async def forgot_password(payload: ForgotPasswordIn) -> ApiResponse[Any]:
    await service.forgot_password(payload.email)
    return ok(None, Msg.AUTH_RESET_REQUESTED)


@router.post(
    "/reset-password",
    response_model=ApiResponse[dict[str, Any]],
    summary="Reset password",
    description="Consume a reset token, set a new password, and log out everywhere.",
    dependencies=[Depends(by_ip(RateBucket.LOGIN_IP))],
)
async def reset_password(payload: ResetPasswordIn) -> ApiResponse[Any]:
    await service.reset_password(payload)
    return ok(None, Msg.AUTH_PASSWORD_CHANGED)
