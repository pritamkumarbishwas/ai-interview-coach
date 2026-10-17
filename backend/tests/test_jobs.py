"""Background job queue and worker tests (persistent, Mongo-backed)."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from app.core.jobs import DONE, FAILED, PENDING, RUNNING, JobQueue, JobWorker
from app.repositories.base import to_object_id
from tests.conftest import _with_mongo

Work = Callable[[object], Awaitable[None]]


def _utcnow_naive() -> datetime:
    # MongoDB returns naive UTC datetimes, so compare in the same frame.
    return datetime.now(UTC).replace(tzinfo=None)


def _run(work: Work):
    """Run an async function against the suite database (fresh loop+client)."""
    box: dict = {}

    async def runner(db) -> None:
        box["value"] = await work(db)

    _with_mongo(runner)
    return box.get("value")


def _queue(**kwargs) -> JobQueue:
    return JobQueue(collection_name=f"jobs_test_{uuid.uuid4().hex[:8]}", **kwargs)


def test_enqueue_then_claim_and_complete() -> None:
    queue = _queue()

    async def work(db) -> None:
        job_id = await queue.enqueue(db, "email.send", {"to": "a@b.c"})
        job = await queue.claim(db)
        assert job is not None and job.id == job_id
        assert job.status == RUNNING
        assert job.attempts == 1
        assert job.payload == {"to": "a@b.c"}
        await queue.complete(db, job_id)
        done = await queue.get(db, job_id)
        assert done is not None and done.status == DONE
        # Nothing left to claim.
        assert await queue.claim(db) is None
        await db[queue._collection_name].drop()

    _run(work)


def test_future_job_is_not_claimed_until_due() -> None:
    queue = _queue()

    async def work(db) -> None:
        future = datetime.now(UTC) + timedelta(hours=1)
        await queue.enqueue(db, "later", run_at=future)
        assert await queue.claim(db) is None
        await db[queue._collection_name].drop()

    _run(work)


def test_failed_job_retries_with_backoff_then_fails() -> None:
    queue = _queue(backoff_seconds=5.0)

    async def work(db) -> None:
        job_id = await queue.enqueue(db, "flaky", max_attempts=2)
        collection = db[queue._collection_name]

        job = await queue.claim(db)
        assert job is not None and job.attempts == 1
        await queue.fail(db, job_id, "boom")
        retried = await queue.get(db, job_id)
        assert retried is not None and retried.status == PENDING
        # Rescheduled into the future (backoff), so not claimable yet.
        assert retried.run_at > _utcnow_naive()
        assert await queue.claim(db) is None

        # Force the due time into the past to simulate the backoff elapsing.
        await collection.update_one(
            {"_id": to_object_id(job_id)},
            {"$set": {"run_at": datetime.now(UTC) - timedelta(seconds=1)}},
        )
        job2 = await queue.claim(db)
        assert job2 is not None and job2.attempts == 2
        await queue.fail(db, job_id, "boom again")
        final = await queue.get(db, job_id)
        assert final is not None and final.status == FAILED
        assert final.last_error is not None and "boom again" in final.last_error
        await collection.drop()

    _run(work)


def test_stats_counts_by_status() -> None:
    queue = _queue()

    async def work(db) -> None:
        await queue.enqueue(db, "a")
        await queue.enqueue(db, "b")
        assert (await queue.stats(db))[PENDING] == 2

        claimed = await queue.claim(db)  # oldest (by run_at, then created_at)
        assert claimed is not None
        after_claim = await queue.stats(db)
        assert after_claim[RUNNING] == 1
        assert after_claim[PENDING] == 1

        await queue.complete(db, claimed.id)
        done_stats = await queue.stats(db)
        assert done_stats[DONE] == 1
        assert done_stats[RUNNING] == 0
        assert done_stats[PENDING] == 1
        await db[queue._collection_name].drop()

    _run(work)


def test_worker_runs_registered_handler() -> None:
    queue = _queue()
    worker = JobWorker(queue)
    seen: list[dict] = []

    async def handler(db, payload) -> None:
        seen.append(payload)

    worker.register("greet", handler)

    async def work(db) -> None:
        await queue.enqueue(db, "greet", {"n": 1})
        assert await worker.run_once(db) is True
        assert await worker.run_once(db) is False
        await db[queue._collection_name].drop()

    _run(work)
    assert seen == [{"n": 1}]


def test_worker_fails_job_without_handler() -> None:
    queue = _queue()
    worker = JobWorker(queue)  # no handlers registered

    async def work(db) -> None:
        job_id = await queue.enqueue(db, "unknown", max_attempts=1)
        assert await worker.run_once(db) is True
        job = await queue.get(db, job_id)
        assert job is not None and job.status == FAILED
        assert job.last_error is not None and "No handler" in job.last_error
        await db[queue._collection_name].drop()

    _run(work)


def test_worker_records_handler_exception() -> None:
    queue = _queue()
    worker = JobWorker(queue)

    async def boom(db, payload) -> None:
        raise RuntimeError("nope")

    worker.register("boom", boom)

    async def work(db) -> None:
        job_id = await queue.enqueue(db, "boom", max_attempts=1)
        assert await worker.run_once(db) is True
        job = await queue.get(db, job_id)
        assert job is not None and job.status == FAILED
        assert job.last_error is not None and "nope" in job.last_error
        await db[queue._collection_name].drop()

    _run(work)


def test_job_survives_a_worker_restart() -> None:
    """Enqueue in one process; a brand-new queue instance in another claims it."""
    name = f"jobs_test_{uuid.uuid4().hex[:8]}"

    async def enqueue_only(db) -> None:
        await JobQueue(collection_name=name).enqueue(db, "greet", {"n": 7})

    _run(enqueue_only)

    seen: list[dict] = []
    queue = JobQueue(collection_name=name)
    worker = JobWorker(queue)

    async def handler(db, payload) -> None:
        seen.append(payload)

    worker.register("greet", handler)

    async def process(db) -> None:
        assert await worker.run_once(db) is True
        await db[name].drop()

    _run(process)
    assert seen == [{"n": 7}]


def test_concurrent_claims_do_not_double_process() -> None:
    queue = _queue()

    async def work(db) -> None:
        await queue.enqueue(db, "only-once")
        claims = await asyncio.gather(*(queue.claim(db) for _ in range(5)))
        claimed = [job for job in claims if job is not None]
        assert len(claimed) == 1
        await db[queue._collection_name].drop()

    _run(work)
