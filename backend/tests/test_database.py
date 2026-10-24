import pytest

from app.core import database


class FakeDatabase:
    name = "test-db"

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.pings = 0

    async def command(self, name: str) -> None:
        assert name == "ping"
        self.pings += 1
        if self.pings <= self.failures:
            raise RuntimeError("mongo is starting")


@pytest.fixture()
def no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(database, "STARTUP_RETRY_BASE_DELAY_SECONDS", 0)
    monkeypatch.setattr(database.asyncio, "sleep", fake_sleep)
    return sleeps


@pytest.mark.asyncio
async def test_wait_for_mongo_retries_transient_failures(
    no_retry_delay: list[float],
) -> None:
    db = FakeDatabase(failures=2)

    await database.wait_for_mongo(db, attempts=3)

    assert db.pings == 3
    assert len(no_retry_delay) == 2


@pytest.mark.asyncio
async def test_wait_for_mongo_raises_after_exhausting_attempts(
    no_retry_delay: list[float],
) -> None:
    db = FakeDatabase(failures=10)

    with pytest.raises(RuntimeError, match="Could not connect to MongoDB"):
        await database.wait_for_mongo(db, attempts=2)

    assert db.pings == 2
    assert len(no_retry_delay) == 1


@pytest.mark.asyncio
async def test_ensure_indexes_retries_until_success(
    monkeypatch: pytest.MonkeyPatch, no_retry_delay: list[float]
) -> None:
    monkeypatch.setattr(database, "_indexes_ready", False)
    attempts: list[int] = []

    async def flaky_create(db) -> None:
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("index build in progress")

    monkeypatch.setattr(database, "_create_indexes", flaky_create)

    await database.ensure_indexes(object())

    assert len(attempts) == 3
    assert database._indexes_ready is True


@pytest.mark.asyncio
async def test_ensure_indexes_raises_after_exhausting_attempts(
    monkeypatch: pytest.MonkeyPatch, no_retry_delay: list[float]
) -> None:
    monkeypatch.setattr(database, "_indexes_ready", False)
    attempts: list[int] = []

    async def always_fails(db) -> None:
        attempts.append(1)
        raise RuntimeError("index build failed")

    monkeypatch.setattr(database, "_create_indexes", always_fails)

    with pytest.raises(RuntimeError, match="index creation failed"):
        await database.ensure_indexes(object())

    assert len(attempts) == database.STARTUP_MAX_ATTEMPTS
    assert database._indexes_ready is False
