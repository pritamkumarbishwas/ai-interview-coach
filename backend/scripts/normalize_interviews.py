"""Repair legacy interview documents and optionally purge orphaned records.

Usage (from backend/):

    python -m scripts.normalize_interviews
    python -m scripts.normalize_interviews --apply
    python -m scripts.normalize_interviews --apply --purge-orphans

The script is a dry run unless ``--apply`` is passed. It:

* maps legacy difficulty values (easy/medium/hard) to the current scale;
* backfills ``created_at`` from the ObjectId and ``completed_at`` from the
  latest answer/report timestamp for completed interviews;
* turns proctoring off for legacy interviews that never recorded proctoring
  data (interviews with recordings or a real session keep it on);
* with ``--purge-orphans``, removes interviews whose owner no longer exists,
  including their GridFS recordings.

Every write is idempotent, so it is safe to re-run.
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings
from app.services.recording_service import recording_service

DIFFICULTY_ALIASES = {
    "easy": "beginner",
    "medium": "intermediate",
    "hard": "advanced",
}
VALID_DIFFICULTIES = {"beginner", "intermediate", "advanced"}
VALID_PROCTORING_MODES = {"off", "camera_only", "strict"}

PROJECTION = {
    "user_id": 1,
    "role": 1,
    "difficulty": 1,
    "status": 1,
    "created_at": 1,
    "started_at": 1,
    "completed_at": 1,
    "proctoring_mode": 1,
    "proctoring_session": 1,
    "recordings": 1,
    "answers.created_at": 1,
    "answers.evaluation.created_at": 1,
    "report.generated_at": 1,
}


def _as_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _has_proctoring_data(doc: dict) -> bool:
    if doc.get("recordings"):
        return True
    session = doc.get("proctoring_session")
    if not isinstance(session, dict):
        return False
    if session.get("events"):
        return True
    return any(
        session.get(key)
        for key in ("consent_given_at", "started_at", "ended_at")
    )


def _latest_timestamp(doc: dict) -> datetime | None:
    candidates: list[datetime] = []

    def add(value: Any) -> None:
        parsed = _as_utc(value)
        if parsed is not None:
            candidates.append(parsed)

    for answer in doc.get("answers") or []:
        if not isinstance(answer, dict):
            continue
        add(answer.get("created_at"))
        evaluation = answer.get("evaluation")
        if isinstance(evaluation, dict):
            add(evaluation.get("created_at"))
    report = doc.get("report")
    if isinstance(report, dict):
        add(report.get("generated_at"))
    add(doc.get("started_at"))
    add(doc.get("created_at"))
    if isinstance(doc.get("_id"), ObjectId):
        add(doc["_id"].generation_time)
    return max(candidates) if candidates else None


def plan_changes(doc: dict) -> tuple[dict[str, Any], list[str]]:
    """Return the fields to set plus human-readable reasons."""
    changes: dict[str, Any] = {}
    reasons: list[str] = []

    difficulty = doc.get("difficulty")
    normalized_difficulty = DIFFICULTY_ALIASES.get(
        difficulty.strip().lower() if isinstance(difficulty, str) else "",
        difficulty,
    )
    if normalized_difficulty != difficulty:
        changes["difficulty"] = normalized_difficulty
        reasons.append(f"difficulty {difficulty!r} -> {normalized_difficulty!r}")

    if _as_utc(doc.get("created_at")) is None:
        object_id = doc.get("_id")
        if isinstance(object_id, ObjectId):
            changes["created_at"] = object_id.generation_time
            reasons.append("created_at backfilled from ObjectId")

    if doc.get("status") == "completed" and _as_utc(doc.get("completed_at")) is None:
        completed_at = _latest_timestamp(doc)
        if completed_at is not None:
            changes["completed_at"] = completed_at
            reasons.append("completed_at backfilled")

    mode = doc.get("proctoring_mode")
    has_data = _has_proctoring_data(doc)
    if mode not in VALID_PROCTORING_MODES:
        replacement = "strict" if has_data else "off"
        changes["proctoring_mode"] = replacement
        reasons.append(f"proctoring_mode {mode!r} -> {replacement!r}")
    elif changes and not has_data and mode != "off":
        changes["proctoring_mode"] = "off"
        reasons.append(f"proctoring_mode {mode!r} -> 'off' (no recorded data)")

    return changes, reasons


async def _orphan_ids(db: AsyncIOMotorDatabase) -> list[str]:
    owners = {str(doc["_id"]) async for doc in db.users.find({}, {"_id": 1})}
    orphans: list[str] = []
    async for doc in db.interviews.find({}, {"_id": 1, "user_id": 1}):
        # Historical writes may have stored the owner as an ObjectId.
        if str(doc.get("user_id")) not in owners:
            orphans.append(str(doc["_id"]))
    return orphans


async def migrate(
    *, apply: bool, purge_orphans: bool, max_details: int = 100
) -> tuple[int, int]:
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        db = client[settings.mongo_db_name]
        changed = 0
        printed = 0
        async for doc in db.interviews.find({}, PROJECTION).sort("_id", 1):
            changes, reasons = plan_changes(doc)
            if not changes:
                continue
            changed += 1
            if apply:
                await db.interviews.update_one(
                    {"_id": doc["_id"]}, {"$set": changes}
                )
            if printed < max_details:
                printed += 1
                verb = "updated" if apply else "would update"
                print(f"  {verb} {doc['_id']} ({doc.get('role') or 'untitled'})")
                for reason in reasons:
                    print(f"    - {reason}")
                if printed == max_details:
                    print(f"  ... details truncated after {max_details} documents")

        orphans = await _orphan_ids(db)
        purged = 0
        if purge_orphans and orphans:
            if apply:
                for interview_id in orphans:
                    await recording_service.purge_interview_recordings(
                        db, interview_id
                    )
                result = await db.interviews.delete_many(
                    {"_id": {"$in": [ObjectId(value) for value in orphans]}}
                )
                purged = result.deleted_count
                print(f"  deleted {purged} orphaned interview(s)")
            else:
                print(
                    f"  would delete {len(orphans)} orphaned interview(s) "
                    "(--apply required)"
                )

        mode = "applied" if apply else "dry run"
        orphan_note = "" if purge_orphans else " (pass --purge-orphans to delete)"
        print(
            f"Done ({mode}): matched={changed}, "
            f"orphans={len(orphans)}{orphan_note}, purged={purged}"
        )
        return changed, purged
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the repairs (default is a dry run)",
    )
    parser.add_argument(
        "--purge-orphans",
        action="store_true",
        help="Also delete interviews whose owner no longer exists",
    )
    parser.add_argument(
        "--max-details",
        type=int,
        default=100,
        help="Maximum number of per-document details to print",
    )
    args = parser.parse_args()
    asyncio.run(
        migrate(
            apply=args.apply,
            purge_orphans=args.purge_orphans,
            max_details=max(1, args.max_details),
        )
    )


if __name__ == "__main__":
    main()
