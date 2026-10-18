"""Phase 8: outbound, HMAC-signed ATS webhooks."""

import hashlib
import hmac
import json
from datetime import UTC, datetime

from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.handlers import register_default_handlers
from app.core.jobs import JobQueue, JobWorker
from app.core.webhooks import WebhookDelivery, sign
from app.integrations import ats
from app.models.invitation import ScreeningInvitation
from app.models.job import Job
from tests.conftest import _with_mongo
from tests.test_scorecard import _job_with_rubric, _patch_llm, _run_candidate_flow
from tests.test_shortlist import _invite, _token


def _run(work):
    box: dict = {}

    async def runner(db) -> None:
        box["value"] = await work(db)

    _with_mongo(runner)
    return box.get("value")


def _job() -> Job:
    return Job(id="job-1", user_id="u1", title="Backend Engineer", company="Acme")


def _invitation(decision: str = "advance") -> ScreeningInvitation:
    return ScreeningInvitation(
        id="inv-1",
        job_id="job-1",
        guest_user_id="guest_x",
        jd_id="jd-1",
        candidate_name="Grace Hopper",
        candidate_email="grace@example.com",
        token_hash="h",
        role="Backend Engineer",
        company="Acme",
        expires_at=datetime.now(UTC),
        created_by="u1",
        decision=decision,
        decision_note="strong signal",
        decided_at=datetime.now(UTC),
    )


def test_signature_is_hmac_of_timestamp_and_body() -> None:
    body = b'{"event":"candidate.decided"}'
    digest = sign("s3cr3t", body, "1700000000")
    expected = hmac.new(b"s3cr3t", b"1700000000." + body, hashlib.sha256).hexdigest()
    assert digest == expected


def test_payload_envelope_and_provider_blocks() -> None:
    job, invitation = _job(), _invitation()

    generic = ats.build_payload(
        "generic", job, invitation, overall_score=72.0, meets_threshold=True
    )
    assert generic["event"] == "candidate.decided"
    assert generic["provider"] == "generic"
    assert generic["candidate"]["email"] == "grace@example.com"
    assert generic["decision"]["value"] == "advance"
    assert generic["assessment"] == {
        "overall_score": 72.0,
        "meets_threshold": True,
        "advisory": True,
    }
    assert "data" not in generic

    greenhouse = ats.build_payload(
        "greenhouse", job, invitation, overall_score=72.0, meets_threshold=True
    )
    assert greenhouse["data"]["type"] == "candidate_stage_change"
    assert greenhouse["data"]["action"] == "advance"
    assert greenhouse["data"]["candidate"] == {
        "first_name": "Grace",
        "last_name": "Hopper",
        "email": "grace@example.com",
    }

    lever = ats.build_payload(
        "lever", job, invitation, overall_score=None, meets_threshold=None
    )
    assert lever["data"]["advance"] is True
    assert lever["data"]["posting"]["title"] == "Backend Engineer"

    # A decline maps to `false` for Lever and to the decline action for Greenhouse.
    declined = _invitation("decline")
    assert (
        ats.build_payload(
            "lever", job, declined, overall_score=None, meets_threshold=None
        )["data"]["advance"]
        is False
    )
    assert (
        ats.build_payload(
            "greenhouse", job, declined, overall_score=None, meets_threshold=None
        )["data"]["action"]
        == "decline"
    )


def test_job_webhook_config_hides_secret(client: TestClient, staff_headers: dict) -> None:
    job_id = _job_with_rubric(client, staff_headers)

    response = client.patch(
        f"/api/jobs/{job_id}",
        headers=staff_headers,
        json={
            "webhook_url": "https://partner.example/hook",
            "webhook_provider": "greenhouse",
            "webhook_secret": "s3cr3t",
            "webhook_enabled": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["webhook_url"] == "https://partner.example/hook"
    assert body["webhook_provider"] == "greenhouse"
    assert body["webhook_enabled"] is True
    assert body["webhook_configured"] is True
    assert "webhook_secret" not in body  # the secret never leaves the server

    # Enabling without a URL is rejected; a non-http scheme is a validation error.
    assert (
        client.patch(
            f"/api/jobs/{job_id}", headers=staff_headers, json={"webhook_enabled": True}
        ).status_code
        == 200  # already configured above, so still valid
    )
    assert (
        client.patch(
            f"/api/jobs/{job_id}",
            headers=staff_headers,
            json={"webhook_url": "ftp://nope"},
        ).status_code
        == 422
    )


def test_enabling_webhook_without_url_is_rejected(
    client: TestClient, staff_headers: dict
) -> None:
    job_id = _job_with_rubric(client, staff_headers)
    response = client.patch(
        f"/api/jobs/{job_id}", headers=staff_headers, json={"webhook_enabled": True}
    )
    assert response.status_code == 422
    assert "URL" in response.json()["detail"]


def test_decide_queues_webhook_and_worker_delivers_it(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    def clear_queue(db):
        return db[settings.jobs_collection_name].delete_many({})

    _run(clear_queue)

    _patch_llm(monkeypatch, [])
    job_id = _job_with_rubric(client, staff_headers)
    invitation = _invite(client, staff_headers, job_id, "hook@example.com")
    _run_candidate_flow(client, _token(invitation))

    client.patch(
        f"/api/jobs/{job_id}",
        headers=staff_headers,
        json={
            "webhook_url": "https://partner.example/hook",
            "webhook_provider": "greenhouse",
            "webhook_secret": "s3cr3t",
            "webhook_enabled": True,
        },
    )
    decided = client.patch(
        f"/api/invitations/{invitation['id']}/decision",
        headers=staff_headers,
        json={"decision": "advance", "note": "great"},
    )
    assert decided.status_code == 200, decided.text

    sent: list[WebhookDelivery] = []

    async def fake_send(delivery: WebhookDelivery) -> int:
        sent.append(delivery)
        return 200

    monkeypatch.setattr("app.core.webhooks.webhook_sender.send", fake_send)

    worker = JobWorker(JobQueue())
    register_default_handlers(worker)
    assert _run(lambda db: worker.run_once(db)) is True

    assert len(sent) == 1
    delivery = sent[0]
    assert delivery.url == "https://partner.example/hook"
    assert delivery.event == "candidate.decided"
    assert delivery.secret == "s3cr3t"
    assert delivery.payload["decision"]["value"] == "advance"
    assert delivery.payload["provider"] == "greenhouse"
    # Advisory score pulled from the stored evaluations (no LLM call).
    assert delivery.payload["assessment"]["overall_score"] == 72.0

    # The delivery job completed and is not re-queued.
    assert _run(lambda db: worker.run_once(db)) is False


def test_decide_without_webhook_queues_nothing(
    client: TestClient, staff_headers: dict
) -> None:
    _run(lambda db: db[settings.jobs_collection_name].delete_many({}))
    job_id = _job_with_rubric(client, staff_headers)
    invitation = _invite(client, staff_headers, job_id, "quiet@example.com")

    response = client.patch(
        f"/api/invitations/{invitation['id']}/decision",
        headers=staff_headers,
        json={"decision": "hold"},
    )
    assert response.status_code == 200
    count = _run(lambda db: db[settings.jobs_collection_name].count_documents({}))
    assert count == 0


def test_delivery_payload_is_signed_with_the_job_secret() -> None:
    """The signature a partner would verify covers the exact delivered body."""
    job = _job()
    job.webhook_url = "https://partner.example/hook"
    job.webhook_secret = "s3cr3t"
    body = json.dumps(
        ats.build_payload("generic", job, _invitation(), overall_score=None, meets_threshold=None),
        separators=(",", ":"),
        default=str,
    ).encode()
    assert sign("s3cr3t", body, "1700000000") == hmac.new(
        b"s3cr3t", b"1700000000." + body, hashlib.sha256
    ).hexdigest()


def test_webhook_secret_is_encrypted_at_rest(
    client: TestClient, staff_headers: dict, monkeypatch
) -> None:
    """With a key configured, the signing secret is ciphertext on disk."""
    import app.core.handlers as handlers_module
    import app.services.job_service as job_service_module
    from app.core.crypto import PREFIX, FieldCipher

    cipher = FieldCipher("unit-test-key")
    monkeypatch.setattr(job_service_module, "field_cipher", cipher)
    monkeypatch.setattr(handlers_module, "field_cipher", cipher)

    _patch_llm(monkeypatch, [])
    job_id = _job_with_rubric(client, staff_headers)
    invitation = _invite(client, staff_headers, job_id, "sealed@example.com")
    _run_candidate_flow(client, _token(invitation))

    client.patch(
        f"/api/jobs/{job_id}",
        headers=staff_headers,
        json={
            "webhook_url": "https://partner.example/hook",
            "webhook_provider": "generic",
            "webhook_secret": "s3cr3t",
            "webhook_enabled": True,
        },
    )

    stored = _run(lambda db: db.jobs.find_one({"_id": ObjectId(job_id)}))
    assert stored["webhook_secret"].startswith(PREFIX)
    assert "s3cr3t" not in stored["webhook_secret"]

    client.patch(
        f"/api/invitations/{invitation['id']}/decision",
        headers=staff_headers,
        json={"decision": "advance"},
    )

    sent: list[WebhookDelivery] = []

    async def fake_send(delivery: WebhookDelivery) -> int:
        sent.append(delivery)
        return 200

    monkeypatch.setattr("app.core.webhooks.webhook_sender.send", fake_send)

    worker = JobWorker(JobQueue())
    register_default_handlers(worker)
    assert _run(lambda db: worker.run_once(db)) is True

    # The delivered signature uses the decrypted secret, not the ciphertext.
    assert sent and sent[0].secret == "s3cr3t"
