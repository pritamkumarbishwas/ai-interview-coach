from collections.abc import Awaitable, Callable

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_db
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import decode_access_token
from app.core.usage import usage_actor
from app.models.api_key import ApiKey
from app.models.user import STAFF_ROLES, User
from app.repositories.api_key_repository import api_key_repository
from app.repositories.interview_repository import interview_repository
from app.repositories.invitation_repository import invitation_repository
from app.repositories.job_description_repository import job_description_repository
from app.repositories.job_repository import job_repository
from app.repositories.resume_repository import resume_repository
from app.repositories.staff_invitation_repository import staff_invitation_repository
from app.repositories.template_repository import template_repository
from app.repositories.user_repository import UserRepository, user_repository
from app.services.api_key_service import ApiKeyService
from app.services.audit_service import AuditService, audit_service
from app.services.auth_service import AuthService
from app.services.dashboard_service import DashboardService
from app.services.interview_service import InterviewService
from app.services.job_description_service import JobDescriptionService
from app.services.job_service import JobService
from app.services.quota_service import QuotaService, quota_service
from app.services.recording_service import RecordingService, recording_service
from app.services.resume_service import ResumeService
from app.services.retention_service import RetentionService, retention_service
from app.services.screening_service import ScreeningService
from app.services.staff_service import StaffService
from app.services.template_service import TemplateService

bearer_scheme = HTTPBearer(auto_error=False)
# Public API auth: a long-lived key sent in `X-API-Key` (never a bearer token).
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_user_repository() -> UserRepository:
    return user_repository


def get_auth_service(
    users: UserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(users)


def get_resume_service() -> ResumeService:
    """Repositories are stateless, so a fresh service per request is cheap."""
    return ResumeService(resume_repository)


def get_job_description_service() -> JobDescriptionService:
    return JobDescriptionService(job_description_repository)


def get_job_service() -> JobService:
    return JobService(job_repository, template_repository, user_repository)


def get_template_service() -> TemplateService:
    return TemplateService(template_repository, job_repository)


def get_interview_service() -> InterviewService:
    return InterviewService(interview_repository, resume_repository, job_description_repository)


def get_recording_service() -> RecordingService:
    return recording_service


def get_dashboard_service() -> DashboardService:
    return DashboardService(interview_repository)


def get_screening_service() -> ScreeningService:
    return ScreeningService(
        invitation_repository,
        job_repository,
        template_repository,
        job_description_repository,
        interview_repository,
        get_interview_service(),
        get_recording_service(),
    )


def get_staff_service() -> StaffService:
    return StaffService(user_repository, staff_invitation_repository)


def get_api_key_service() -> ApiKeyService:
    return ApiKeyService(api_key_repository)


def get_retention_service() -> RetentionService:
    return retention_service


def get_audit_service() -> AuditService:
    return audit_service


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncIOMotorDatabase = Depends(get_db),
    users: UserRepository = Depends(get_user_repository),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Not authenticated")

    payload = decode_access_token(credentials.credentials)
    user = await users.get_by_id(db, payload.sub)
    if user is None:
        raise AuthenticationError("User no longer exists")
    # Attribute any LLM usage in this request to the acting user.
    usage_actor.set(user.id)
    return user


def require_roles(*allowed: str) -> Callable[..., Awaitable[User]]:
    """Dependency factory: allow only the given roles (else 403)."""

    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise AuthorizationError("You do not have permission to perform this action")
        return current_user

    return dependency


require_staff = require_roles(*STAFF_ROLES)
require_admin = require_roles("admin")
require_recruiter = require_roles("admin", "recruiter")


def get_quota_service() -> QuotaService:
    return quota_service


def require_quota(
    action: str, guard: Callable[..., Awaitable[User]] = require_staff
) -> Callable[..., Awaitable[User]]:
    """Dependency factory: run `guard`, then consume one unit of `action`.

    Raises 429 when the caller's role has exhausted its daily quota. The guarded
    user is returned so the handler can reuse it (``get_current_user`` is cached
    per request).
    """

    async def dependency(
        user: User = Depends(guard),
        db: AsyncIOMotorDatabase = Depends(get_db),
        service: QuotaService = Depends(get_quota_service),
    ) -> User:
        await service.enforce(db, user, action)
        return user

    return dependency


async def require_api_key(
    api_key: str | None = Security(api_key_scheme),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ApiKeyService = Depends(get_api_key_service),
) -> ApiKey:
    """Authenticate a public-API request via its `X-API-Key` header."""
    return await service.authenticate(db, api_key)
