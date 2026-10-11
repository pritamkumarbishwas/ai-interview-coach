"""Recording pipeline tests: auth, ownership, chunked upload/download, finalize.

Uses the shared `env` fixture (a real interview created through the API with a
mocked LLM) so the recordings attach to a genuine interview document rather than
a hand-inserted one. Verifies the byte-identical round-trip, finalize metadata,
seq=0 crash-tolerant restart, the size cap, and content-type validation.
"""

import uuid

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from tests.conftest import Env, _with_mongo


def upload_chunk(
    client: TestClient,
    headers: dict,
    interview_id: str,
    *,
    kind: str = "camera",
    seq: int = 0,
    finalize: bool = False,
    content_type: str = "video/webm",
    blob: bytes = b"\x00\x01\x02",
):
    return client.post(
        f"/api/interviews/{interview_id}/recordings/chunk",
        headers=headers,
        data={
            "kind": kind,
            "seq": str(seq),
            "finalize": "true" if finalize else "false",
            "content_type": content_type,
        },
        files={"chunk": ("chunk.webm", blob, content_type)},
    )


def test_requires_auth(client: TestClient) -> None:
    iid = "0" * 24
    r = client.post(
        f"/api/interviews/{iid}/recordings/chunk",
        data={"kind": "camera", "seq": "0", "finalize": "false", "content_type": "video/webm"},
        files={"chunk": ("c.webm", b"x", "video/webm")},
    )
    assert r.status_code == 401
    assert client.get(f"/api/interviews/{iid}/recordings/camera").status_code == 401


def test_nonexistent_interview_is_404(
    client: TestClient, auth_headers: dict
) -> None:
    iid = "0" * 24
    assert upload_chunk(client, auth_headers, iid).status_code == 404
    assert (
        client.get(f"/api/interviews/{iid}/recordings/camera", headers=auth_headers).status_code
        == 404
    )


def test_unknown_kind_is_404(client: TestClient, auth_headers: dict, env: Env) -> None:
    ctx = env.setup()
    r = client.get(
        f"/api/interviews/{ctx['id']}/recordings/bogus", headers=auth_headers
    )
    assert r.status_code == 404


def test_upload_and_download_round_trip(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup()
    iid = ctx["id"]

    c0 = bytes(range(256)) * 40  # 10240 bytes
    c1 = bytes((i * 7) % 256 for i in range(5000))
    c2 = b"FINAL-" + uuid.uuid4().bytes

    for seq, blob, fin in [(0, c0, False), (1, c1, False), (2, c2, True)]:
        r = upload_chunk(
            client, auth_headers, iid, seq=seq, finalize=fin, blob=blob
        )
        assert r.status_code == 204, r.text

    r = client.get(f"/api/interviews/{iid}/recordings/camera", headers=auth_headers)
    assert r.status_code == 200
    assert r.content == c0 + c1 + c2
    assert r.headers["content-type"].startswith("video/webm")


def test_finalize_writes_recording_meta(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup()
    iid = ctx["id"]
    blob = b"meta-check" * 100
    assert (
        upload_chunk(client, auth_headers, iid, seq=0, finalize=True, blob=blob).status_code
        == 204
    )

    meta = {}

    async def lookup(db):
        doc = await db.interviews.find_one({"_id": ObjectId(iid)})
        meta.update((doc or {}).get("recordings", {}).get("camera", {}))

    _with_mongo(lookup)
    assert meta["finalized"] is True
    assert meta["size_bytes"] == len(blob)
    assert meta["chunk_count"] == 1


def test_seq_zero_restarts_upload(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup()
    iid = ctx["id"]

    # First recording: two chunks.
    upload_chunk(client, auth_headers, iid, seq=0, blob=b"OLD-A" * 50)
    upload_chunk(client, auth_headers, iid, seq=1, finalize=True, blob=b"OLD-B" * 50)

    # Restart at seq=0 with new bytes; old chunks must be discarded.
    new0, new1 = b"NEW-A" * 50, b"NEW-B" * 50
    assert upload_chunk(client, auth_headers, iid, seq=0, blob=new0).status_code == 204
    assert (
        upload_chunk(client, auth_headers, iid, seq=1, finalize=True, blob=new1).status_code
        == 204
    )

    r = client.get(f"/api/interviews/{iid}/recordings/camera", headers=auth_headers)
    assert r.content == new0 + new1


def test_screen_kind_is_independent_of_camera(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup()
    iid = ctx["id"]
    cam, scr = b"CAMERA-DATA", b"SCREEN-DATA"
    upload_chunk(client, auth_headers, iid, kind="camera", finalize=True, blob=cam)
    upload_chunk(client, auth_headers, iid, kind="screen", finalize=True, blob=scr)

    assert (
        client.get(f"/api/interviews/{iid}/recordings/camera", headers=auth_headers).content
        == cam
    )
    assert (
        client.get(f"/api/interviews/{iid}/recordings/screen", headers=auth_headers).content
        == scr
    )


def test_non_owner_cannot_upload_or_download(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup()
    iid = ctx["id"]
    upload_chunk(client, auth_headers, iid, seq=0, finalize=True, blob=b"owner-data")

    # A second, distinct user must not see or touch this recording.
    other_email = f"other.{uuid.uuid4().hex[:8]}@ex.com"
    created = client.post(
        "/api/auth/register",
        json={"name": "Other", "email": other_email, "password": "pw12345678"},
    )
    assert created.status_code == 201
    login = client.post(
        "/api/auth/login", json={"email": other_email, "password": "pw12345678"}
    )
    assert login.status_code == 200
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert upload_chunk(client, other_headers, iid).status_code == 404
    assert (
        client.get(f"/api/interviews/{iid}/recordings/camera", headers=other_headers).status_code
        == 404
    )


def test_oversized_chunk_is_413(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    from app.core.config import settings

    ctx = env.setup()
    over = b"0" * (settings.max_recording_chunk_bytes + 1)
    r = upload_chunk(client, auth_headers, ctx["id"], blob=over)
    assert r.status_code == 413


def test_unsupported_content_type_rejected(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup()
    r = upload_chunk(
        client, auth_headers, ctx["id"], content_type="text/html", blob=b"<html>"
    )
    assert r.status_code in (400, 413, 415, 422)


def test_download_before_finalize_is_404(
    client: TestClient, auth_headers: dict, env: Env
) -> None:
    ctx = env.setup()
    # Chunks uploaded but never finalized -> no sealed recording to download.
    upload_chunk(client, auth_headers, ctx["id"], seq=0, finalize=False, blob=b"partial")
    r = client.get(
        f"/api/interviews/{ctx['id']}/recordings/camera", headers=auth_headers
    )
    assert r.status_code == 404
