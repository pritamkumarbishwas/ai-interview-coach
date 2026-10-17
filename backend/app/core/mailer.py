"""Outbound email: a provider-agnostic abstraction with a safe default.

Nothing is actually sent unless a transport provider is configured. The default
``console`` provider logs the message, so local/dev flows work end to end and a
mistake can never leak real email. Tests use :class:`MemoryMailer` to capture
what would have been sent.

Providers are selected by ``MAIL_PROVIDER`` (see ``app.core.config``). Adding a
real transport (SMTP, SES, ...) means implementing :class:`Mailer`, registering
the name in ``SUPPORTED_MAIL_PROVIDERS``, and extending :func:`build_mailer`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import SUPPORTED_MAIL_PROVIDERS, settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    """A fully rendered email ready to hand to a transport."""

    to: str
    subject: str
    text: str
    html: str | None = None
    from_email: str | None = None
    from_name: str | None = None

    def resolved_sender(self) -> str:
        """``"Name <address>"`` using per-message overrides, else settings."""
        name = (self.from_name or settings.mail_from_name).strip()
        address = (self.from_email or settings.mail_from).strip()
        return f"{name} <{address}>" if name else address


class Mailer(ABC):
    """Transport seam: everything that needs to send email depends on this."""

    @abstractmethod
    async def send(self, message: EmailMessage) -> None:
        """Deliver ``message``. Raises on transport failure."""


class ConsoleMailer(Mailer):
    """Default provider: log the message, send nothing."""

    async def send(self, message: EmailMessage) -> None:
        logger.info(
            "Email (console) to=%s from=%s subject=%r",
            message.to,
            message.resolved_sender(),
            message.subject,
        )


class MemoryMailer(Mailer):
    """In-process capture — used by tests and dry runs (never in production)."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)

    def clear(self) -> None:
        self.sent.clear()


def build_mailer(provider: str | None = None) -> Mailer:
    """Construct the mailer for ``provider`` (defaults to the configured one)."""
    choice = (provider or settings.mail_provider).strip().lower()
    if choice == "console":
        return ConsoleMailer()
    raise ValueError(
        f"Unsupported MAIL_PROVIDER={choice!r}. "
        f"Valid options: {', '.join(SUPPORTED_MAIL_PROVIDERS)}."
    )


def get_mailer() -> Mailer:
    """The application-wide mailer (built once from settings)."""
    return _mailer


_mailer: Mailer = build_mailer()
