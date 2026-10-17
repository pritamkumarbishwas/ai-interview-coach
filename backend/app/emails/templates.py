"""Transactional email templates.

Templates are plain functions returning an :class:`EmailContent` (subject +
text + html). Every value interpolated into the HTML body is escaped, because
names, roles, and company strings originate from user input.
"""

from dataclasses import dataclass
from datetime import datetime
from html import escape


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str
    html: str


def _row(label: str, value: str) -> str:
    return (
        '<tr>'
        f'<td style="padding:4px 12px 4px 0;color:#6b7280;font-size:13px;">{escape(label)}</td>'
        '<td style="padding:4px 0;color:#111827;font-size:13px;'
        f'font-weight:600;">{escape(value)}</td>'
        "</tr>"
    )


def _shell(heading: str, intro: str, body_rows: str, cta_label: str, cta_url: str) -> str:
    return (
        '<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;'
        'max-width:520px;margin:0 auto;padding:24px;">'
        f'<h1 style="font-size:20px;color:#111827;margin:0 0 12px;">{escape(heading)}</h1>'
        '<p style="font-size:14px;color:#374151;line-height:1.5;margin:0 0 16px;">'
        f"{escape(intro)}</p>"
        '<table style="border-collapse:collapse;margin:0 0 20px;">'
        f"{body_rows}"
        "</table>"
        f'<a href="{escape(cta_url)}" style="display:inline-block;background:#d97706;'
        'color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;'
        f'padding:10px 18px;border-radius:8px;">{escape(cta_label)}</a>'
        '<p style="font-size:12px;color:#9ca3af;margin:20px 0 0;">'
        "If the button does not work, copy this link into your browser:</p>"
        f'<p style="font-size:12px;color:#6b7280;word-break:break-all;margin:4px 0 0;">'
        f"{escape(cta_url)}</p>"
        "</div>"
    )


def invitation_email(
    *,
    candidate_name: str,
    role: str,
    company: str,
    interview_url: str,
    expires_at: datetime | None = None,
) -> EmailContent:
    """Invite a candidate to a first-round AI interview (magic link)."""
    greeting = candidate_name.strip() or "there"
    expiry_line = (
        f"\nThis link expires on {expires_at:%Y-%m-%d %H:%M UTC}."
        if expires_at is not None
        else ""
    )
    text = (
        f"Hi {greeting},\n\n"
        f"{company} has invited you to a first-round interview for the {role} role.\n"
        "You can complete it in your browser \u2014 no account needed.\n\n"
        f"Start your interview: {interview_url}{expiry_line}\n\n"
        "Good luck,\n"
        f"The {company} hiring team"
    )
    rows = _row("Role", role) + _row("Company", company)
    if expires_at is not None:
        rows += _row("Expires", f"{expires_at:%Y-%m-%d %H:%M UTC}")
    html = _shell(
        "Your interview invitation",
        f"Hi {greeting}, {company} has invited you to a first-round interview for "
        f"the {role} role. Complete it in your browser \u2014 no account needed.",
        rows,
        "Start interview",
        interview_url,
    )
    return EmailContent(
        subject=f"Interview invitation: {role} at {company}",
        text=text,
        html=html,
    )


def reminder_email(
    *,
    candidate_name: str,
    role: str,
    company: str,
    interview_url: str,
    expires_at: datetime | None = None,
) -> EmailContent:
    """Nudge a candidate who has not started/completed their interview yet."""
    greeting = candidate_name.strip() or "there"
    expiry_line = (
        f"\nPlease complete it before {expires_at:%Y-%m-%d %H:%M UTC}."
        if expires_at is not None
        else ""
    )
    text = (
        f"Hi {greeting},\n\n"
        f"This is a reminder to complete your first-round interview for the "
        f"{role} role at {company}.\n\n"
        f"Resume your interview: {interview_url}{expiry_line}\n\n"
        "Good luck,\n"
        f"The {company} hiring team"
    )
    rows = _row("Role", role) + _row("Company", company)
    if expires_at is not None:
        rows += _row("Complete by", f"{expires_at:%Y-%m-%d %H:%M UTC}")
    html = _shell(
        "Interview reminder",
        f"Hi {greeting}, this is a reminder to complete your first-round interview "
        f"for the {role} role at {company}.",
        rows,
        "Resume interview",
        interview_url,
    )
    return EmailContent(
        subject=f"Reminder: your {role} interview at {company}",
        text=text,
        html=html,
    )
