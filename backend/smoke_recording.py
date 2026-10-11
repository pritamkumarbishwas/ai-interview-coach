"""In-process smoke test for the recording pipeline.

Runs against the real FastAPI app + real MongoDB via TestClient (no network
server). Verifies auth, ownership, the chunked upload/download round-trip
(byte-identical), finalize metadata, seq=0 restart, size cap, and unsupported
content type. Cleans up all created documents afterwards.

Mongo async ops are batched into a single asyncio.run to keep the motor client
on one event loop; TestClient HTTP calls are synchronous and independent.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from bson import ObjectId
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket

from app.core.config import settings
from app.main import app

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}  {detail}")


def register_and_login(client: TestClient, tag: str) -> tuple[str, str]:
    email = f"{tag}-{uuid.uuid4().hex[:8]}@smoke.dev"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "Password123!", "name": "Smoke"},
    )
    r = client.post(
        "/api/auth/login", json={"email": email, "password": "Password123!"}
    )
    assert r.status_code == 200, r.text
    return email, r.json()["access_token"]


async def _mongo_setup(email_a: str):
    """Insert one interview owned by email_a and return (user_a_id, iid)."""
    mclient = AsyncIOMotorClient(settings.mongo_uri)
    db = mclient[settings.mongo_db_name]
    ua = await db.users.find_one({"email": email_a})
    if ua is None:
        raise RuntimeError(f"owner user not found: {email_a}")
    iid = uuid.uuid4().hex[:24]
    await db.interviews.insert_one(
        {
            "_id": ObjectId(iid),
            # find_owned queries user_id as a plain string, so store it as one.
            "user_id": str(ua["_id"]),
            # Interview model requires resume_id/jd_id; dummy values suffice.
            "resume_id": uuid.uuid4().hex[:24],
            "jd_id": uuid.uuid4().hex[:24],
            "role": "Backend Engineer",
            "level": "mid",
            "type": "technical",
            "difficulty": "intermediate",
            "proctoring_mode": "strict",
            "target_questions": 3,
            "status": "completed",
            "questions": [],
            "answers": [],
            "recordings": {},
            "overall_score": None,
            "created_at": datetime.now(UTC),
        }
    )
    mclient.close()
    return str(ua["_id"]), iid


async def _mongo_meta(iid: str):
    mclient = AsyncIOMotorClient(settings.mongo_uri)
    db = mclient[settings.mongo_db_name]
    doc = await db.interviews.find_one({"_id": ObjectId(iid)})
    mclient.close()
    return (doc or {}).get("recordings", {}).get("camera")


async def _mongo_cleanup(iid: str, email_regex: str):
    mclient = AsyncIOMotorClient(settings.mongo_uri)
    db = mclient[settings.mongo_db_name]
    await db.interviews.delete_one({"_id": ObjectId(iid)})
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name=settings.recording_bucket_name)
    cursor = bucket.find({"filename": {"$regex": f"^{iid}:"}})
    ids = [g._id async for g in cursor]
    for gid in ids:
        await bucket.delete(gid)
    await db.users.delete_many({"email": {"$regex": email_regex}})
    mclient.close()


def run() -> int:
    global PASS, FAIL
    client = TestClient(app)
    with client:
        tok_a = register_and_login(client, "usera")
        tok_b = register_and_login(client, "userb")
        email_a = tok_a[0]
        tok_a = tok_a[1]
        tok_b = tok_b[1]
        h_a = {"Authorization": f"Bearer {tok_a}"}
        h_b = {"Authorization": f"Bearer {tok_b}"}

        print("== auth ==")
        r = client.post(
            "/api/interviews/000000000000000000000000/recordings/chunk",
            data={
                "kind": "camera",
                "seq": "0",
                "finalize": "false",
                "content_type": "video/webm",
            },
            files={"chunk": ("c.webm", b"x", "video/webm")},
        )
        check("upload without token -> 401", r.status_code == 401, f"got {r.status_code}")
        r = client.get("/api/interviews/000000000000000000000000/recordings/camera")
        check("download without token -> 401", r.status_code == 401, f"got {r.status_code}")

        print("== nonexistent / bad kind ==")
        r = client.post(
            "/api/interviews/000000000000000000000000/recordings/chunk",
            headers=h_a,
            data={
                "kind": "camera",
                "seq": "0",
                "finalize": "false",
                "content_type": "video/webm",
            },
            files={"chunk": ("c.webm", b"x", "video/webm")},
        )
        check("upload nonexistent interview -> 404", r.status_code == 404, f"got {r.status_code}")
        r = client.get("/api/interviews/000000000000000000000000/recordings/camera", headers=h_a)
        check("download nonexistent interview -> 404", r.status_code == 404, f"got {r.status_code}")
        r = client.get("/api/interviews/000000000000000000000000/recordings/bogus", headers=h_a)
        check("download bad kind -> 404", r.status_code == 404, f"got {r.status_code}")

        # Set up a real interview owned by A (user ids + iid via mongo).
        _, iid = asyncio.run(_mongo_setup(email_a))

        print("== ownership (A owns, B does not) ==")
        # B is not the owner -> find_owned returns None -> 404.
        r = client.post(
            f"/api/interviews/{iid}/recordings/chunk",
            headers=h_b,
            data={
                "kind": "camera",
                "seq": "0",
                "finalize": "false",
                "content_type": "video/webm",
            },
            files={"chunk": ("c.webm", b"x", "video/webm")},
        )
        check("upload non-owner -> 404 (find_owned)", r.status_code == 404, f"got {r.status_code}")
        r = client.get(f"/api/interviews/{iid}/recordings/camera", headers=h_b)
        check("download non-owner -> 404 (find_owned)", r.status_code == 404, f"got {r.status_code}")

        print("== round-trip ==")
        c0 = bytes(range(256)) * 40  # 10240 bytes
        c1 = bytes((i * 7) % 256 for i in range(5000))
        c2 = b"FINAL-CHUNK-" + uuid.uuid4().bytes
        for seq, blob, fin in [(0, c0, "false"), (1, c1, "false"), (2, c2, "true")]:
            r = client.post(
                f"/api/interviews/{iid}/recordings/chunk",
                headers=h_a,
                data={
                    "kind": "camera",
                    "seq": str(seq),
                    "finalize": fin,
                    "content_type": "video/webm",
                },
                files={"chunk": ("c.webm", blob, "video/webm")},
            )
            check(
                f"upload chunk seq={seq} finalize={fin} -> 204",
                r.status_code == 204,
                f"got {r.status_code} {r.text[:200]}",
            )

        expected = c0 + c1 + c2
        r = client.get(f"/api/interviews/{iid}/recordings/camera", headers=h_a)
        check("download finalized recording -> 200", r.status_code == 200, f"got {r.status_code}")
        check(
            "downloaded bytes byte-identical",
            r.content == expected,
            f"len got={len(r.content)} want={len(expected)}",
        )
        check(
            "content-type preserved",
            r.headers.get("content-type", "").startswith("video/webm"),
            f"got {r.headers.get('content-type')}",
        )

        meta = asyncio.run(_mongo_meta(iid))
        check(
            "finalize wrote RecordingMeta",
            meta is not None and meta.get("finalized") is True,
            f"got {meta}",
        )
        check(
            "meta.size_bytes == total",
            meta is not None and meta.get("size_bytes") == len(expected),
            f"got {meta.get('size_bytes') if meta else None} want {len(expected)}",
        )
        check(
            "meta.chunk_count == 3",
            meta is not None and meta.get("chunk_count") == 3,
            f"got {meta.get('chunk_count') if meta else None}",
        )

        print("== seq=0 restart ==")
        d0 = b"RESTART-A" * 100
        d1 = b"RESTART-B" * 100
        for seq, blob, fin in [(0, d0, "false"), (1, d1, "true")]:
            r = client.post(
                f"/api/interviews/{iid}/recordings/chunk",
                headers=h_a,
                data={
                    "kind": "camera",
                    "seq": str(seq),
                    "finalize": fin,
                    "content_type": "video/webm",
                },
                files={"chunk": ("c.webm", blob, "video/webm")},
            )
            check(f"restart upload seq={seq} -> 204", r.status_code == 204, f"got {r.status_code}")
        r = client.get(f"/api/interviews/{iid}/recordings/camera", headers=h_a)
        check(
            "restart replaced old data",
            r.content == d0 + d1,
            f"len got={len(r.content)} want={len(d0)+len(d1)}",
        )

        print("== size cap / content type ==")
        over = b"0" * (settings.max_recording_chunk_bytes + 1)
        r = client.post(
            f"/api/interviews/{iid}/recordings/chunk",
            headers=h_a,
            data={
                "kind": "camera",
                "seq": "0",
                "finalize": "false",
                "content_type": "video/webm",
            },
            files={"chunk": ("big.webm", over, "video/webm")},
        )
        check("oversized chunk -> 413", r.status_code == 413, f"got {r.status_code}")
        r = client.post(
            f"/api/interviews/{iid}/recordings/chunk",
            headers=h_a,
            data={
                "kind": "camera",
                "seq": "0",
                "finalize": "false",
                "content_type": "text/html",
            },
            files={"chunk": ("c.html", b"<html>", "text/html")},
        )
        check(
            "unsupported content type -> rejected",
            r.status_code in (400, 413, 415, 422),
            f"got {r.status_code}",
        )

    asyncio.run(_mongo_cleanup(iid, "^(usera|userb)-"))

    print(f"\nRESULT: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(run())
