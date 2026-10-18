"""Shared requisition access rules.

A requisition is reachable by three kinds of staff:

- its **owner** (the recruiter who created it),
- any **admin** (cross-owner override), and
- a **reviewer** the recruiter assigned to it (``reviewer_ids``).

Everyone else — a recruiter who happens to guess another owner's job id — is
treated as if the row does not exist, so access failures never leak existence.
Reviewers are read/decide only, hence the split between ``*_accessible`` (read)
and ``*_manageable`` (mutate) lookups.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.user import User
from app.repositories.job_repository import JobRepository


def can_access_job(job_doc: dict, actor: User) -> bool:
    """True if `actor` may *read* the requisition (owner, admin, or reviewer)."""
    if actor.role == "admin":
        return True
    if job_doc.get("user_id") == actor.id:
        return True
    return (actor.id or "") in (job_doc.get("reviewer_ids") or [])


def can_manage_job(job_doc: dict, actor: User) -> bool:
    """True if `actor` may *mutate* the requisition (owner or admin only)."""
    return actor.role == "admin" or job_doc.get("user_id") == actor.id


async def find_accessible_job(
    db: AsyncIOMotorDatabase,
    jobs: JobRepository,
    job_id: str,
    actor: User,
) -> dict | None:
    """Return the requisition if `actor` may read it, else `None`."""
    doc = await jobs.find_owned(db, job_id, actor.id or "")
    if doc is not None:
        return doc
    if actor.role == "admin":
        return await jobs.get_by_id(db, job_id)
    doc = await jobs.get_by_id(db, job_id)
    if doc is not None and can_access_job(doc, actor):
        return doc
    return None


async def find_manageable_job(
    db: AsyncIOMotorDatabase,
    jobs: JobRepository,
    job_id: str,
    actor: User,
) -> dict | None:
    """Return the requisition if `actor` may mutate it, else `None`."""
    doc = await jobs.find_owned(db, job_id, actor.id or "")
    if doc is not None:
        return doc
    if actor.role == "admin":
        return await jobs.get_by_id(db, job_id)
    return None
