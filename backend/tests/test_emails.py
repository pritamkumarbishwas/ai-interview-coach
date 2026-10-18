import asyncio
import logging
from datetime import UTC, datetime

import pytest

from app.core.config import settings
from app.core.mailer import ConsoleMailer, EmailMessage, MemoryMailer, build_mailer
from app.emails.templates import invitation_email, reminder_email


def test_invitation_email_includes_link_and_details() -> None:
    content = invitation_email(
        candidate_name="Ada",
        role="Backend Engineer",
        company="Acme",
        interview_url="https://example.com/i/abc123",
    )
    assert "Backend Engineer" in content.subject
    assert "Acme" in content.subject
    assert "https://example.com/i/abc123" in content.text
    assert "https://example.com/i/abc123" in content.html
    assert "Ada" in content.text
    assert content.html.startswith("<div")


def test_invitation_email_escapes_user_input_in_html() -> None:
    content = invitation_email(
        candidate_name="<script>alert(1)</script>",
        role="X & Y",
        company='Acme "<b>"',
        interview_url="https://example.com/i/abc123",
    )
    # HTML is escaped; the raw markup never reaches the html body.
    assert "<script>" not in content.html
    assert "&lt;script&gt;" in content.html
    assert "X &amp; Y" in content.html


def test_invitation_email_mentions_expiry_when_provided() -> None:
    expires = datetime(2026, 1, 2, 15, 30, tzinfo=UTC)
    content = invitation_email(
        candidate_name="Ada",
        role="Backend Engineer",
        company="Acme",
        interview_url="https://example.com/i/abc123",
        expires_at=expires,
    )
    assert "2026-01-02 21:00 IST" in content.text
    assert "2026-01-02 21:00 IST" in content.html


def test_invitation_email_without_name_still_greets() -> None:
    content = invitation_email(
        candidate_name="   ",
        role="Backend Engineer",
        company="Acme",
        interview_url="https://example.com/i/abc123",
    )
    assert "Hi there," in content.text


def test_reminder_email_renders_link_and_deadline() -> None:
    expires = datetime(2026, 3, 4, 9, 0, tzinfo=UTC)
    content = reminder_email(
        candidate_name="Ada",
        role="Data Scientist",
        company="Globex",
        interview_url="https://example.com/i/xyz",
        expires_at=expires,
    )
    assert "Reminder" in content.subject
    assert "https://example.com/i/xyz" in content.text
    assert "2026-03-04 14:30 IST" in content.text


def test_resolved_sender_uses_settings_defaults() -> None:
    message = EmailMessage(to="a@b.c", subject="s", text="t")
    sender = message.resolved_sender()
    assert settings.mail_from in sender
    assert settings.mail_from_name in sender


def test_per_message_sender_override_wins() -> None:
    message = EmailMessage(
        to="a@b.c", subject="s", text="t", from_name="Support", from_email="help@x.io"
    )
    assert message.resolved_sender() == "Support <help@x.io>"


def test_build_mailer_defaults_to_console() -> None:
    assert isinstance(build_mailer(), ConsoleMailer)
    assert isinstance(build_mailer("console"), ConsoleMailer)


def test_build_mailer_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="MAIL_PROVIDER"):
        build_mailer("smtp")


def test_memory_mailer_captures_and_clears() -> None:
    mailer = MemoryMailer()

    async def work() -> None:
        await mailer.send(EmailMessage(to="a@b.c", subject="s", text="t"))

    asyncio.run(work())
    assert len(mailer.sent) == 1
    mailer.clear()
    assert mailer.sent == []


def test_console_mailer_logs_without_sending(caplog: pytest.LogCaptureFixture) -> None:
    mailer = ConsoleMailer()

    async def work() -> None:
        await mailer.send(EmailMessage(to="a@b.c", subject="hi", text="t"))

    with caplog.at_level(logging.INFO):
        asyncio.run(work())
    assert any("a@b.c" in record.getMessage() for record in caplog.records)
