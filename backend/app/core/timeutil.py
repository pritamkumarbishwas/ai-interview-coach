"""Display timezone helpers.

Timestamps are stored and reasoned about in **UTC** (MongoDB stores instants as
UTC; Motor hands them back naive). ``Asia/Kolkata`` (IST) is used only for what
humans read: email/PDF copy, log timestamps, API JSON, and the frontend.

IST is a fixed +05:30 offset with no daylight saving, so a plain ``timezone``
works everywhere and avoids the ``tzdata`` dependency ``ZoneInfo`` needs on
Windows. Naive datetimes are assumed to be UTC (which is exactly what the
database returns), so they convert correctly.
"""

from datetime import UTC, datetime, timedelta, timezone
from typing import Annotated

from pydantic import PlainSerializer

# India Standard Time — fixed offset, no DST.
IST = timezone(timedelta(hours=5, minutes=30))


def to_ist(value: datetime) -> datetime:
    """Return ``value`` as an aware datetime in IST.

    A naive value is treated as UTC (the frame MongoDB returns).
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(IST)


def ist_isoformat(value: datetime) -> str:
    """ISO-8601 rendering of ``value`` in IST (e.g. ``...+05:30``)."""
    return to_ist(value).isoformat()


# Response-schema field type: validates as ``datetime`` but serializes to an
# IST ISO string when the model is dumped to JSON. ``when_used="json"`` keeps
# ``model_dump()`` (used for MongoDB writes) returning real datetimes.
ISTDateTime = Annotated[
    datetime,
    PlainSerializer(ist_isoformat, return_type=str, when_used="json"),
]
