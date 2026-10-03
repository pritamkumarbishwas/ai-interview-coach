from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.job_description import JobDescription
from app.models.user import User
from app.prompts.templates import EXTRACT_JD_INFO_PROMPT
from app.schemas.job_description import (
    JobDescriptionInput,
    JobDescriptionResponse,
    JobDescriptionStructuredData,
    JobDescriptionSummary,
)
from app.services.llm_service import llm_service

router = APIRouter()

SNIPPET_LENGTH = 180


def _snippet(text: str, length: int = SNIPPET_LENGTH) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= length else compact[: length - 1].rstrip() + "…"


@router.post("", response_model=JobDescriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_job_description(
    payload: JobDescriptionInput,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> JobDescriptionResponse:
    prompt = EXTRACT_JD_INFO_PROMPT.format(text=payload.raw_text)
    structured_data = await llm_service.generate_structured(prompt, JobDescriptionStructuredData)

    jd = JobDescription(
        user_id=current_user.id,
        title=payload.title.strip(),
        company=payload.company.strip(),
        raw_text=payload.raw_text,
        snippet=_snippet(payload.raw_text),
        structured_data=structured_data.model_dump(),
    )
    result = await db.job_descriptions.insert_one(jd.model_dump(by_alias=True, exclude={"id"}))
    jd.id = str(result.inserted_id)

    return JobDescriptionResponse(
        id=jd.id,
        title=jd.title,
        company=jd.company,
        structured_data=structured_data,
    )


@router.get("", response_model=list[JobDescriptionSummary])
async def list_job_descriptions(
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[JobDescriptionSummary]:
    cursor = (
        db.job_descriptions.find({"user_id": current_user.id}, {"raw_text": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    summaries: list[JobDescriptionSummary] = []
    async for doc in cursor:
        summaries.append(
            JobDescriptionSummary(
                id=str(doc["_id"]),
                title=doc.get("title", ""),
                company=doc.get("company", ""),
                snippet=snippet_of(doc),
                created_at=doc["created_at"],
            )
        )
    return summaries


@router.get("/{jd_id}", response_model=JobDescription)
async def get_job_description(
    jd_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> JobDescription:
    doc = await _find_job_description(db, jd_id, current_user.id)
    doc["_id"] = str(doc["_id"])
    return JobDescription(**doc)


@router.delete("/{jd_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_description(
    jd_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> None:
    doc = await _find_job_description(db, jd_id, current_user.id)
    await db.job_descriptions.delete_one({"_id": doc["_id"]})


def snippet_of(doc: dict) -> str:
    snippet = doc.get("snippet")
    if snippet:
        return snippet
    # Legacy documents: rebuild something useful from the stored structure.
    data = doc.get("structured_data") or {}
    parts = list(data.get("responsibilities", []))
    return _snippet(", ".join(parts))


async def _find_job_description(db: AsyncIOMotorDatabase, jd_id: str, user_id: str) -> dict:
    try:
        object_id = ObjectId(jd_id)
    except (InvalidId, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found"
        ) from None
    doc = await db.job_descriptions.find_one({"_id": object_id, "user_id": user_id})
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job description not found"
        )
    return doc
