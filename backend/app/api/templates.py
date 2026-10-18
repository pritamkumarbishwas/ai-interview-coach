from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_template_service, require_recruiter
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.models.user import User
from app.schemas.template import (
    TemplateCreate,
    TemplateOut,
    TemplatePreviewOut,
    TemplatePreviewRequest,
    TemplateSummary,
    TemplateUpdate,
)
from app.services.template_service import TemplateService

router = APIRouter()


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateCreate,
    current_user: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: TemplateService = Depends(get_template_service),
    _: None = Depends(rate_limit("template_create")),
) -> TemplateOut:
    return await service.create(db, current_user.id, payload)


@router.get("", response_model=list[TemplateSummary])
async def list_templates(
    current_user: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: TemplateService = Depends(get_template_service),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[TemplateSummary]:
    return await service.list(db, current_user.id, limit)


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(
    template_id: str,
    current_user: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: TemplateService = Depends(get_template_service),
) -> TemplateOut:
    return await service.get(db, current_user.id, template_id)


@router.patch("/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: str,
    payload: TemplateUpdate,
    current_user: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: TemplateService = Depends(get_template_service),
) -> TemplateOut:
    return await service.update(db, current_user.id, template_id, payload)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    current_user: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: TemplateService = Depends(get_template_service),
) -> None:
    await service.delete(db, current_user.id, template_id)


@router.post("/{template_id}/preview", response_model=TemplatePreviewOut)
async def preview_template_question(
    template_id: str,
    payload: TemplatePreviewRequest,
    current_user: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: TemplateService = Depends(get_template_service),
    _: None = Depends(rate_limit("template_preview")),
) -> TemplatePreviewOut:
    return await service.preview_question(db, current_user.id, template_id, payload)
