"""Phase 9: data retention and right-to-erasure."""

from datetime import UTC, datetime, timedelta

from bson import ObjectId
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from app.core.config import settings
from app.core.handlers import register_default_handlers
from app.core.jobs import JobQueue, JobWorker
from app.services.retention_service import RETENTION_PURGE_JOB
from tests.conftest import _with_mongo
from tests.test_scorecard import _job_with_rubric, _patch_llm, _run_candidate_flow
from tests.test_shortlist import _invite, _token


def _run(work):
    box: dict = {}

    async def runner(db) -> None:
        box["value"] = await work(db)

    _with_mongo(runner)
    return box.get("value")


def _completed_candidate(
    client: TestClient, headers: dict, monkeypatch, email: str
) -> tuple[str, str]:
    """Create a job + invitation, run the candidate to completion.

    Returns ``(invitation_id, interview_id)``.
    """
    _patch_llm(monkeypatch, [])
    job_id = _job_with_rubric(client, headers)
    invitation = _invite(client, headers, job_id, email)
    _run_candidate_flow(client, _token(invitation))

    async def interview_id_for(db) -> str:
        doc = await db.screening_invitations.find_one({"_id": ObjectId(invitation["id"])})
        return doc["interview_id"]

    return invitation["id"], _run(interview_id_for)


def _add_recording_chunk(interview_id: str, payload: bytes = b"video-bytes") -> None:
    async def add(db) -> None:
        grid = AsyncIOMotorGridFSBucket(db, bucket_name=settings.recording_bucket_name)
        stream = grid.open_upload_stream(
            f"{interview_id}:camera#0", metadata={"interview_id": interview_id}
        )
        await stream.write(payload)
        await stream.close()

    _run(add)


def _snapshot(invitation_id: str, interview_id: str) -> dict:
    async def read(db) -> dict:
        invite = await db.screening_invitations.find_one({"_id": ObjectId(invitation_id)})
        interviews = await db.interviews.count_documents({"_id": ObjectId(interview_id)})
        files = await db[f"{settings.recording_bucket_name}.files"].count_documents(
            {"filename": {"$regex": f"^{interview_id}:"}}
        )
        return {"invite": invite, "interviews": interviews, "chunks": files}

    return _run(read)


def test_erase_candidate_destroys_session_data(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    invitation_id, interview_id = _completed_candidate(
        client, staff_headers, monkeypatch, "erase-me@example.com"
    )
    _add_recording_chunk(interview_id)
    jd_id = _run(lambda db: _jd_for(db, interview_id))

    response = client.post(
        f"/api/invitations/{invitation_id}/erase", headers=staff_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["interview_deleted"] is True
    assert body["recording_chunks_deleted"] == 1

    state = _snapshot(invitation_id, interview_id)
    assert state["interviews"] == 0
    assert state["chunks"] == 0
    assert state["invite"]["candidate_name"] == "[erased]"
    assert state["invite"]["candidate_email"].endswith("@erased.invalid")
    assert state["invite"]["interview_id"] is None
    assert state["invite"]["status"] == "revoked"
    assert state["invite"]["erased_at"] is not None
    # The candidate's synthesized job description is purged with the session.
    assert _run(lambda db: db.job_descriptions.count_documents({"_id": ObjectId(jd_id)})) == 0


async def _jd_for(db, interview_id: str) -> str:
    doc = await db.interviews.find_one({"_id": ObjectId(interview_id)})
    return doc["jd_id"]


def test_erase_is_idempotent_and_recruiter_gated(
    client: TestClient, staff_headers: dict, auth_headers: dict, monkeypatch
) -> None:
    invitation_id, _ = _completed_candidate(
        client, staff_headers, monkeypatch, "twice@example.com"
    )
    url = f"/api/invitations/{invitation_id}/erase"

    assert client.post(url, headers=auth_headers).status_code == 403

    first = client.post(url, headers=staff_headers)
    assert first.status_code == 200, first.text
    second = client.post(url, headers=staff_headers)
    assert second.status_code == 200
    assert second.json()["interview_deleted"] is False
    assert second.json()["recording_chunks_deleted"] == 0

    assert (
        client.post(
            "/api/invitations/64b000000000000000000000/erase", headers=staff_headers
        ).status_code
        == 404
    )


def test_purge_only_erases_data_past_the_window(
    client: TestClient, staff_headers: dict, admin_headers: dict, monkeypatch
) -> None:
    old_id, _ = _completed_candidate(
        client, staff_headers, monkeypatch, "old@example.com"
    )
    fresh_id, _ = _completed_candidate(
        client, staff_headers, monkeypatch, "fresh@example.com"
    )

    past = datetime.now(UTC) - timedelta(days=settings.data_retention_days + 10)

    async def backdate(db) -> None:
        await db.screening_invitations.update_one(
            {"_id": ObjectId(old_id)}, {"$set": {"completed_at": past}}
        )

    _run(backdate)

    # Recruiters cannot trigger a global purge; admins can.
    assert (
        client.post(
            "/api/invitations/retention/purge", headers=staff_headers
        ).status_code
        == 403
    )
    response = client.post("/api/invitations/retention/purge", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["erased"] == 1

    async def state(db) -> dict:
        return {
            str(doc["_id"]): doc.get("erased_at")
            async for doc in db.screening_invitations.find({})
        }

    rows = _run(state)
    assert rows[old_id] is not None
    assert rows[fresh_id] is None


def test_retention_purge_job_handler_runs(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    _run(lambda db: db[settings.jobs_collection_name].delete_many({}))
    old_id, _ = _completed_candidate(
        client, staff_headers, monkeypatch, "scheduled@example.com"
    )
    past = datetime.now(UTC) - timedelta(days=settings.data_retention_days + 10)

    async def backdate_and_enqueue(db) -> None:
        await db.screening_invitations.update_one(
            {"_id": ObjectId(old_id)}, {"$set": {"completed_at": past}}
        )
        await JobQueue().enqueue(db, RETENTION_PURGE_JOB, {})

    _run(backdate_and_enqueue)

    worker = JobWorker(JobQueue())
    register_default_handlers(worker)
    assert _run(lambda db: worker.run_once(db)) is True

    async def erased(db) -> object:
        doc = await db.screening_invitations.find_one({"_id": ObjectId(old_id)})
        return doc.get("erased_at")

    assert _run(erased) is not None
