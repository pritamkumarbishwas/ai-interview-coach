"""Persistent background job queue backed by MongoDB.

Job state lives in a Mongo collection (not in memory), so an enqueued job
survives a process restart. A worker atomically claims one due job at a time,
runs the registered handler for its type, and marks it done — or reschedules it
with backoff until ``max_attempts`` is exhausted, then marks it failed.

The worker is opt-in: nothing polls unless ``JOBS_ENABLED`` is set (or a worker
is started in code, as the tests do). Enqueue/claim is safe under concurrency
because claiming uses a single atomic ``find_one_and_update``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.core.config import settings
from app.repositories.base import stringify_id, to_object_id

logger = logging.getLogger(__name__)

JobHandler = Callable[[AsyncIOMotorDatabase, dict], Awaitable[Any]]

PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"


@dataclass
class Job:
    id: str
    type: str
    payload: dict
    status: str
    attempts: int
    max_attempts: int
    run_at: datetime
    created_at: datetime
    updated_at: datetime
    last_error: str | None = None

    @classmethod
    def from_doc(cls, doc: dict) -> Job:
        return cls(
            id=str(doc["_id"]),
            type=doc["type"],
            payload=doc.get("payload") or {},
            status=doc["status"],
            attempts=int(doc.get("attempts", 0)),
            max_attempts=int(doc.get("max_attempts", 1)),
            run_at=doc["run_at"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            last_error=doc.get("last_error"),
        )


class JobQueue:
    """Mongo-backed queue of background jobs."""

    def __init__(
        self,
        collection_name: str | None = None,
        *,
        backoff_seconds: float | None = None,
    ) -> None:
        self._collection_name = collection_name or settings.jobs_collection_name
        self._backoff_seconds = (
            backoff_seconds if backoff_seconds is not None else settings.jobs_backoff_seconds
        )

    def _collection(self, db: AsyncIOMotorDatabase):
        return db[self._collection_name]

    async def ensure_indexes(self, db: AsyncIOMotorDatabase) -> None:
        """Index the claim query: pending jobs ordered by their due time."""
        await self._collection(db).create_index(
            [("status", 1), ("run_at", 1)], name="ix_jobs_status_run_at"
        )

    async def enqueue(
        self,
        db: AsyncIOMotorDatabase,
        job_type: str,
        payload: dict | None = None,
        *,
        run_at: datetime | None = None,
        max_attempts: int | None = None,
    ) -> str:
        now = datetime.now(UTC)
        doc = {
            "type": job_type,
            "payload": payload or {},
            "status": PENDING,
            "attempts": 0,
            "max_attempts": max_attempts or settings.jobs_max_attempts,
            "run_at": run_at or now,
            "created_at": now,
            "updated_at": now,
            "last_error": None,
        }
        result = await self._collection(db).insert_one(doc)
        return str(result.inserted_id)

    async def claim(self, db: AsyncIOMotorDatabase) -> Job | None:
        """Atomically claim the next due pending job, or ``None`` if none."""
        now = datetime.now(UTC)
        doc = await self._collection(db).find_one_and_update(
            {"status": PENDING, "run_at": {"$lte": now}},
            {"$set": {"status": RUNNING, "updated_at": now}, "$inc": {"attempts": 1}},
            sort=[("run_at", 1), ("created_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        return Job.from_doc(doc) if doc else None

    async def complete(self, db: AsyncIOMotorDatabase, job_id: str) -> None:
        object_id = to_object_id(job_id)
        if object_id is None:
            return
        await self._collection(db).update_one(
            {"_id": object_id},
            {"$set": {"status": DONE, "updated_at": datetime.now(UTC), "last_error": None}},
        )

    async def fail(self, db: AsyncIOMotorDatabase, job_id: str, error: str) -> None:
        """Retry with backoff until attempts are exhausted, then mark failed."""
        object_id = to_object_id(job_id)
        if object_id is None:
            return
        doc = await self._collection(db).find_one({"_id": object_id})
        if doc is None:
            return
        now = datetime.now(UTC)
        attempts = int(doc.get("attempts", 0))
        exhausted = attempts >= int(doc.get("max_attempts", 1))
        update: dict[str, Any] = {
            "status": FAILED if exhausted else PENDING,
            "updated_at": now,
            "last_error": error[:2000],
        }
        if not exhausted:
            # Exponential-ish backoff: attempts * base (attempts already bumped
            # by the claim that led to this failure).
            update["run_at"] = now + timedelta(seconds=self._backoff_seconds * attempts)
        await self._collection(db).update_one({"_id": object_id}, {"$set": update})

    async def stats(self, db: AsyncIOMotorDatabase) -> dict[str, int]:
        """Counts per status (missing statuses default to 0)."""
        pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        counts = {PENDING: 0, RUNNING: 0, DONE: 0, FAILED: 0}
        async for row in self._collection(db).aggregate(pipeline):
            counts[str(row["_id"])] = int(row["count"])
        return counts

    async def get(self, db: AsyncIOMotorDatabase, job_id: str) -> Job | None:
        object_id = to_object_id(job_id)
        if object_id is None:
            return None
        doc = await self._collection(db).find_one({"_id": object_id})
        return Job.from_doc(stringify_id(doc)) if doc else None


class JobWorker:
    """Runs registered handlers for queued jobs, one at a time."""

    def __init__(self, queue: JobQueue | None = None) -> None:
        self._queue = queue or job_queue
        self._handlers: dict[str, JobHandler] = {}
        self._stop = asyncio.Event()

    def register(self, job_type: str, handler: JobHandler) -> None:
        self._handlers[job_type] = handler

    def handlers(self) -> dict[str, JobHandler]:
        return dict(self._handlers)

    async def run_once(self, db: AsyncIOMotorDatabase) -> bool:
        """Process at most one job. Returns whether a job was handled."""
        job = await self._queue.claim(db)
        if job is None:
            return False
        handler = self._handlers.get(job.type)
        if handler is None:
            await self._queue.fail(
                db, job.id, f"No handler registered for job type {job.type!r}"
            )
            return True
        try:
            await handler(db, job.payload)
        except Exception as exc:  # handlers are independently untrusted
            logger.warning(
                "Job %s (%s) failed: %s: %s",
                job.id,
                job.type,
                type(exc).__name__,
                exc,
            )
            await self._queue.fail(db, job.id, f"{type(exc).__name__}: {exc}")
        else:
            await self._queue.complete(db, job.id)
        return True

    async def run_forever(
        self, db: AsyncIOMotorDatabase, poll_interval: float | None = None
    ) -> None:
        """Poll until :meth:`stop` is called. Never raises out of the loop."""
        interval = (
            poll_interval
            if poll_interval is not None
            else settings.jobs_poll_interval_seconds
        )
        self._stop.clear()
        while not self._stop.is_set():
            try:
                processed = await self.run_once(db)
            except Exception as exc:  # keep the loop alive
                logger.error("Job worker iteration failed: %s: %s", type(exc).__name__, exc)
                processed = False
            if not processed:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=interval)
                except TimeoutError:
                    pass

    def stop(self) -> None:
        self._stop.set()


job_queue = JobQueue()
job_worker = JobWorker(job_queue)
