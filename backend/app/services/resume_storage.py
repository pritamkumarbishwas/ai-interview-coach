"""Durable resume asset storage backed by MongoDB GridFS.

Resume originals, full extracted content and page previews are stored in
GridFS rather than inline MongoDB documents. This keeps each resume document
small, gives the assets the same backup/restore boundary as the database, and
matches how interview recordings are already stored.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from gridfs.errors import NoFile
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorGridFSBucket

from app.core.config import settings

logger = logging.getLogger(__name__)

KIND_ORIGINAL = "original"
KIND_CONTENT = "content"
KIND_PREVIEW = "preview"


def _object_id(value: str) -> ObjectId | None:
    try:
        return ObjectId(value)
    except Exception:
        return None


class ResumeStorage:
    """Small async wrapper around the GridFS buckets used by resumes."""

    def __init__(
        self,
        files_bucket: str | None = None,
        preview_bucket: str | None = None,
    ) -> None:
        self._files_bucket = files_bucket or settings.resume_bucket_name
        self._preview_bucket = preview_bucket or settings.resume_preview_bucket_name

    def _bucket(
        self, db: AsyncIOMotorDatabase, bucket_name: str
    ) -> AsyncIOMotorGridFSBucket:
        return AsyncIOMotorGridFSBucket(db, bucket_name=bucket_name)

    async def put_bytes(
        self,
        db: AsyncIOMotorDatabase,
        *,
        bucket_name: str,
        filename: str,
        data: bytes,
        metadata: dict[str, Any],
    ) -> str:
        bucket = self._bucket(db, bucket_name)
        file_id = await bucket.upload_from_stream(
            filename,
            data,
            metadata={**metadata, "stored_at": datetime.now(UTC).isoformat()},
        )
        return str(file_id)

    async def put_original(
        self,
        db: AsyncIOMotorDatabase,
        *,
        resume_id: str,
        user_id: str,
        filename: str,
        data: bytes,
        sha256: str,
        content_type: str,
    ) -> str:
        return await self.put_bytes(
            db,
            bucket_name=self._files_bucket,
            filename=filename,
            data=data,
            metadata={
                "resume_id": resume_id,
                "user_id": user_id,
                "kind": KIND_ORIGINAL,
                "sha256": sha256,
                "content_type": content_type,
            },
        )

    async def put_content(
        self,
        db: AsyncIOMotorDatabase,
        *,
        resume_id: str,
        user_id: str,
        content: dict[str, Any],
        sha256: str,
    ) -> str:
        data = json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode()
        return await self.put_bytes(
            db,
            bucket_name=self._files_bucket,
            filename=f"{resume_id}.content.json",
            data=data,
            metadata={
                "resume_id": resume_id,
                "user_id": user_id,
                "kind": KIND_CONTENT,
                "sha256": sha256,
                "content_type": "application/json",
            },
        )

    async def put_preview(
        self,
        db: AsyncIOMotorDatabase,
        *,
        resume_id: str,
        user_id: str,
        page: int,
        data: bytes,
        width: int,
        height: int,
        dpi: int,
        content_type: str = "image/png",
    ) -> str:
        return await self.put_bytes(
            db,
            bucket_name=self._preview_bucket,
            filename=f"{resume_id}.page-{page}.png",
            data=data,
            metadata={
                "resume_id": resume_id,
                "user_id": user_id,
                "kind": KIND_PREVIEW,
                "page": page,
                "width": width,
                "height": height,
                "dpi": dpi,
                "content_type": content_type,
            },
        )

    async def get_bytes(
        self, db: AsyncIOMotorDatabase, bucket_name: str, file_id: str
    ) -> bytes | None:
        object_id = _object_id(file_id)
        if object_id is None:
            return None
        bucket = self._bucket(db, bucket_name)
        try:
            stream = await bucket.open_download_stream(object_id)
            return await stream.read()
        except (NoFile, FileNotFoundError):
            return None

    async def get_original(
        self, db: AsyncIOMotorDatabase, file_id: str
    ) -> bytes | None:
        return await self.get_bytes(db, self._files_bucket, file_id)

    async def get_content(
        self, db: AsyncIOMotorDatabase, file_id: str
    ) -> dict[str, Any] | None:
        data = await self.get_bytes(db, self._files_bucket, file_id)
        if data is None:
            return None
        try:
            parsed = json.loads(data)
        except (TypeError, ValueError):
            logger.warning("Stored resume content is not valid JSON: %s", file_id)
            return None
        return parsed if isinstance(parsed, dict) else None

    async def get_preview(
        self, db: AsyncIOMotorDatabase, file_id: str
    ) -> bytes | None:
        return await self.get_bytes(db, self._preview_bucket, file_id)

    async def delete(
        self, db: AsyncIOMotorDatabase, bucket_name: str, file_id: str
    ) -> None:
        object_id = _object_id(file_id)
        if object_id is None:
            return
        bucket = self._bucket(db, bucket_name)
        try:
            await bucket.delete(object_id)
        except NoFile:
            return

    async def delete_original(
        self, db: AsyncIOMotorDatabase, file_id: str
    ) -> None:
        await self.delete(db, self._files_bucket, file_id)

    async def delete_preview(
        self, db: AsyncIOMotorDatabase, file_id: str
    ) -> None:
        await self.delete(db, self._preview_bucket, file_id)


resume_storage = ResumeStorage()
