from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_db
from app.core.exceptions import AuthenticationError
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.interview_repository import interview_repository
from app.repositories.job_description_repository import job_description_repository
from app.repositories.resume_repository import resume_repository
from app.repositories.user_repository import UserRepository, user_repository
from app.services.auth_service import AuthService
from app.services.dashboard_service import DashboardService
from app.services.interview_service import InterviewService
from app.services.job_description_service import JobDescriptionService
from app.services.resume_service import ResumeService

bearer_scheme = HTTPBearer(auto_error=False)


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


def get_interview_service() -> InterviewService:
    return InterviewService(interview_repository, resume_repository, job_description_repository)


def get_dashboard_service() -> DashboardService:
    return DashboardService(interview_repository)


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
    return user
