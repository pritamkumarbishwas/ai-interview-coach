from datetime import UTC, datetime

from bson import ObjectId

from scripts.normalize_interviews import plan_changes


def test_plan_changes_repairs_legacy_fields() -> None:
    object_id = ObjectId()

    changes, reasons = plan_changes(
        {
            "_id": object_id,
            "role": "Backend Engineer",
            "difficulty": "medium",
            "status": "completed",
            "proctoring_mode": "full",
            "answers": [],
        }
    )

    assert changes["difficulty"] == "intermediate"
    assert changes["created_at"] == object_id.generation_time
    assert isinstance(changes["completed_at"], datetime)
    # "full" was never a valid mode, and nothing recorded proctoring data.
    assert changes["proctoring_mode"] == "off"
    assert reasons


def test_plan_changes_keeps_proctoring_when_data_exists() -> None:
    changes, _ = plan_changes(
        {
            "_id": ObjectId(),
            "role": "Backend Engineer",
            "difficulty": "hard",
            "status": "completed",
            "proctoring_mode": "full",
            "recordings": {"camera": {"file_id": "abc"}},
            "answers": [],
        }
    )

    assert changes["difficulty"] == "advanced"
    assert changes["proctoring_mode"] == "strict"


def test_plan_changes_leaves_current_documents_alone() -> None:
    changes, reasons = plan_changes(
        {
            "_id": ObjectId(),
            "role": "Backend Engineer",
            "difficulty": "beginner",
            "status": "created",
            "proctoring_mode": "strict",
            "created_at": datetime.now(UTC),
        }
    )

    assert changes == {}
    assert reasons == []
