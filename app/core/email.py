"""Email sending: a console backend (dev) and an SMTP backend (prod), swappable in tests."""

import logging
from typing import Protocol

from app.core.config import settings

log = logging.getLogger(__name__)


class EmailSender(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleSender:
    """Dev backend: logs the subject and body at INFO."""

    async def send(self, to: str, subject: str, body: str) -> None:
        log.info("email to=%s subject=%s body=%s", to, subject, body)


class SmtpSender:
    def __init__(self) -> None:
        import aiosmtplib

        self._lib = aiosmtplib

    async def send(self, to: str, subject: str, body: str) -> None:
        await self._lib.send(
            message=f"From: {settings.email_from}\nTo: {to}\nSubject: {subject}\n\n{body}",
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password.get_secret_value() if settings.smtp_password else None,
            start_tls=settings.smtp_starttls,
        )


_sender: EmailSender | None = None


def get_sender() -> EmailSender:
    global _sender
    if _sender is None:
        _sender = SmtpSender() if settings.email_backend == "smtp" else ConsoleSender()
    return _sender


def set_sender(sender: EmailSender | None) -> None:
    global _sender
    _sender = sender
