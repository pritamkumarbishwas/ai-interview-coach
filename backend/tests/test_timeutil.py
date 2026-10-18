"""IST display helpers and response-time serialization."""

from datetime import UTC, datetime

from app.core.timeutil import IST, ist_isoformat, to_ist
from app.models.answer import Answer


def test_ist_is_a_fixed_five_thirty_offset() -> None:
    assert IST.utcoffset(None).total_seconds() == 5 * 3600 + 30 * 60


def test_to_ist_converts_aware_utc() -> None:
    converted = to_ist(datetime(2026, 1, 2, 15, 30, tzinfo=UTC))
    assert converted.isoformat() == "2026-01-02T21:00:00+05:30"


def test_to_ist_treats_naive_as_utc() -> None:
    converted = to_ist(datetime(2026, 1, 2, 15, 30))
    assert converted.isoformat() == "2026-01-02T21:00:00+05:30"


def test_ist_isoformat_renders_offset() -> None:
    assert ist_isoformat(datetime(2026, 1, 2, 15, 30, tzinfo=UTC)) == "2026-01-02T21:00:00+05:30"


def test_json_serialization_uses_ist() -> None:
    answer = Answer(
        id="a1",
        question_id="q1",
        text="hi",
        created_at=datetime(2026, 1, 2, 15, 30, tzinfo=UTC),
    )
    assert '"created_at":"2026-01-02T21:00:00+05:30"' in answer.model_dump_json()


def test_model_dump_keeps_datetime_for_storage() -> None:
    answer = Answer(id="a1", question_id="q1", text="hi")
    assert isinstance(answer.model_dump()["created_at"], datetime)
