"""Move legacy local-disk resumes into GridFS and optionally re-analyse them.

Usage (from backend/):

    python -m scripts.migrate_resume_storage
    python -m scripts.migrate_resume_storage --analyze
    python -m scripts.migrate_resume_storage --analyze --delete-local

The migration is idempotent: documents that already have an
`original_file_id` are skipped. Run it before switching off the old
`data/resumes` volume if you need to keep existing uploads.
"""

import argparse
import asyncio
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import resolve_storage_dir, settings
from app.services.resume_processing import resume_processing_service
from app.services.resume_storage import resume_storage


def _safe_local_path(storage_key: str) -> Path | None:
    if not storage_key or "/" in storage_key or "\\" in storage_key:
        return None
    directory = resolve_storage_dir()
    path = directory / storage_key
    return path if path.parent == directory else None


async def migrate(analyze: bool, delete_local: bool) -> int:
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        db = client[settings.mongo_db_name]
        cursor = db.resumes.find(
            {
                "original_file_id": {"$in": [None, ""]},
                "storage_key": {"$exists": True, "$ne": ""},
            }
        )
        migrated = missing = duplicates = 0
        async for doc in cursor:
            resume_id = str(doc["_id"])
            user_id = str(doc.get("user_id") or "")
            storage_key = str(doc.get("storage_key") or "")
            path = _safe_local_path(storage_key)
            if path is None or not path.exists():
                missing += 1
                print(f"  missing local file for {resume_id}: {storage_key or '(none)'}")
                continue

            data = await asyncio.to_thread(path.read_bytes)
            sha256 = hashlib.sha256(data).hexdigest()
            duplicate = await db.resumes.find_one(
                {
                    "_id": {"$ne": doc["_id"]},
                    "user_id": user_id,
                    "sha256": sha256,
                    "analysis.status": {"$ne": "deleting"},
                },
                {"_id": 1},
            )
            if duplicate is not None:
                duplicates += 1
                print(f"  duplicate skipped for {resume_id}: {storage_key}")
                continue

            file_id = await resume_storage.put_original(
                db,
                resume_id=resume_id,
                user_id=user_id,
                filename=str(doc.get("filename") or "resume"),
                data=data,
                sha256=sha256,
                content_type=str(doc.get("mime_type") or "application/octet-stream"),
            )
            fields = {
                "original_file_id": file_id,
                "sha256": sha256,
                "storage_backend": "gridfs",
                "updated_at": datetime.now(UTC),
            }
            if not (doc.get("analysis") or {}).get("status"):
                fields["analysis.status"] = (
                    "ready" if doc.get("structured_data") else "failed"
                )
                if fields["analysis.status"] == "failed":
                    fields["analysis.error_code"] = "analysis_missing"
                    fields["analysis.error_message"] = (
                        "Legacy resume migrated. Re-run analysis to extract sections."
                    )
            await db.resumes.update_one(
                {"_id": doc["_id"]}, {"$set": fields}
            )
            migrated += 1
            print(f"  migrated {resume_id}: {storage_key}")

            if analyze:
                await resume_processing_service.process(db, resume_id, user_id)
                print(f"  analysed {resume_id}")

            if delete_local:
                try:
                    await asyncio.to_thread(path.unlink)
                except OSError as exc:
                    print(f"  could not remove {path}: {exc}")

        print(
            f"Done: migrated={migrated}, duplicates={duplicates}, "
            f"missing={missing}"
        )
        return migrated
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run OCR/preview/LLM extraction after moving each file",
    )
    parser.add_argument(
        "--delete-local",
        action="store_true",
        help="Delete the local file after it has been stored in GridFS",
    )
    args = parser.parse_args()
    asyncio.run(migrate(analyze=args.analyze, delete_local=args.delete_local))


if __name__ == "__main__":
    main()
