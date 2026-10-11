"""Session recording storage: chunked GridFS upload and streamed download.

Interviews record camera (composite) and optionally screen as webm. The
frontend records with `MediaRecorder(timeslice=...)` and uploads each blob as
a chunk; the first chunk (`seq=0`) resets any prior incomplete upload for that
kind, and `finalize=True` seals the file and writes `RecordingMeta` onto the
interview document. Bytes live in GridFS; only metadata is ever returned in
API JSON.
"""

import logging
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorGridFSBucket

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
)
from app.models.interview import Interview, RecordingMeta
from app.repositories.interview_repository import InterviewRepository, interview_repository

logger = logging.getLogger(__name__)

RecordingKind = str  # "camera" | "screen" — validated by the API layer
ALLOWED_RECORDING_KINDS = ("camera", "screen")
ALLOWED_RECORDING_CONTENT_TYPES = ("video/webm", "video/mp4", "video/x-matroska")


class RecordingService:
    def __init__(self, interviews: InterviewRepository) -> None:
        self._interviews = interviews

    def _bucket(self, db: AsyncIOMotorDatabase) -> AsyncIOMotorGridFSBucket:
        return AsyncIOMotorGridFSBucket(db, bucket_name=settings.recording_bucket_name)

    async def append_chunk(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        interview_id: str,
        kind: RecordingKind,
        seq: int,
        chunk: bytes,
        content_type: str,
        finalize: bool,
    ) -> RecordingMeta | None:
        """Append one recorded chunk for (interview, kind).

        `seq=0` deletes any existing GridFS file for that kind and starts a
        fresh upload (crash-tolerant restart). The GridFS file's `metadata`
        tracks `seq` and running `size_bytes` so the total cap is enforced
        across chunks. `finalize=True` writes the sealed `RecordingMeta` to
        the interview document.
        """
        if kind not in ALLOWED_RECORDING_KINDS:
            raise NotFoundError(f"Unknown recording kind: {kind}")
        if content_type not in ALLOWED_RECORDING_CONTENT_TYPES:
            raise PayloadTooLargeError("Unsupported recording content type.")
        if len(chunk) > settings.max_recording_chunk_bytes:
            raise PayloadTooLargeError(
                f"Recording chunk exceeds the "
                f"{settings.max_recording_chunk_bytes // (1024 * 1024)}MB limit."
            )

        # Ownership + existence check (also gates GridFS writes).
        interview = await self._interviews.find_owned(db, interview_id, user_id)
        if interview is None:
            raise NotFoundError("Interview not found")

        bucket = self._bucket(db)
        file_id = f"{interview_id}:{kind}"

        if seq == 0:
            await self._delete_existing(bucket, file_id)

        existing_meta = await self._read_grid_meta(bucket, file_id)
        prev_size = int(existing_meta.get("size_bytes", 0)) if existing_meta else 0
        total = prev_size + len(chunk)
        if total > settings.max_recording_bytes:
            raise PayloadTooLargeError(
                f"Recording exceeds the "
                f"{settings.max_recording_bytes // (1024 * 1024)}MB limit."
            )

        # Open-for-append: GridFS has no native append, so we track the next
        # chunk index in metadata and open a fresh GridIn per chunk with a
        # distinct filename suffix, OR — simpler and robust — store each
        # (interview,kind) as a single logical file by concatenating via
        # `open_upload_stream` with `chunk_index` in metadata. To keep reads
        # simple we instead store ONE GridFS file per chunk and concatenate on
        # download. File id encodes the chunk seq.
        chunk_filename = f"{file_id}#{seq}"
        grid_in = await bucket.open_upload_stream(
            chunk_filename,
            metadata={
                "interview_id": interview_id,
                "kind": kind,
                "seq": seq,
                "size_bytes": len(chunk),
                "content_type": content_type,
            },
        )
        await grid_in.write(chunk)
        await grid_in.close()

        if not finalize:
            return None

        # Finalize: compute total size across this kind's chunks, then write
        # metadata to the interview document (only for the owning user).
        meta = await self._seal(db, user_id, interview_id, kind, content_type)
        return meta

    async def _seal(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        interview_id: str,
        kind: RecordingKind,
        content_type: str,
    ) -> RecordingMeta:
        """Sum this kind's chunks, delete strays, and persist `RecordingMeta`."""
        bucket = self._bucket(db)
        prefix = f"{interview_id}:{kind}#"
        cursor = bucket.find({"filename": {"$regex": f"^{prefix}\\d+$"}})
        total = 0
        count = 0
        async for grid_out in cursor:
            total += int(grid_out.length)
            count += 1

        now = datetime.now(UTC)
        meta = RecordingMeta(
            file_id=f"{interview_id}:{kind}",
            content_type=content_type,
            size_bytes=total,
            chunk_count=count,
            finalized=True,
            created_at=now,
            updated_at=now,
        )
        updated = await self._interviews.set_recording_meta(
            db, interview_id, user_id, kind, meta.model_dump()
        )
        if updated is None:
            raise ConflictError("Interview is no longer available.")
        return meta

    async def read_recording(
        self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str, kind: RecordingKind
    ) -> tuple[bytes, str]:
        """Return the full concatenated recording bytes and content type.

        Chunked GridFS files are concatenated in `seq` order. Ownership is
        enforced via the interview document.
        """
        if kind not in ALLOWED_RECORDING_KINDS:
            raise NotFoundError(f"Unknown recording kind: {kind}")
        doc = await self._interviews.find_owned(db, interview_id, user_id)
        if doc is None:
            raise NotFoundError("Interview not found")
        interview = Interview(**doc)
        meta = interview.recordings.get(kind)
        if meta is None or not meta.finalized:
            raise NotFoundError("Recording not found")

        bucket = self._bucket(db)
        prefix = f"{interview_id}:{kind}#"
        cursor = bucket.find({"filename": {"$regex": f"^{prefix}\\d+$"}})
        chunks: dict[int, bytes] = {}
        async for grid_out in cursor:
            seq = int(str(grid_out.filename).rsplit("#", 1)[-1])
            chunks[seq] = await grid_out.read()
        if not chunks:
            raise NotFoundError("Recording data missing")

        data = b"".join(chunks[seq] for seq in sorted(chunks))
        return data, meta.content_type

    async def _delete_existing(self, bucket: AsyncIOMotorGridFSBucket, file_id: str) -> None:
        """Delete all existing chunks for a logical recording (fresh upload)."""
        prefix = f"{file_id}#"
        cursor = bucket.find({"filename": {"$regex": f"^{prefix}\\d+$"}})
        ids = [grid_out._id async for grid_out in cursor]
        for grid_id in ids:
            try:
                await bucket.delete(grid_id)
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                logger.warning("Failed to delete old recording chunk: %s", exc)

    async def _read_grid_meta(
        self, bucket: AsyncIOMotorGridFSBucket, file_id: str
    ) -> dict | None:
        """Read the running size metadata from the highest-seq chunk, if any."""
        prefix = f"{file_id}#"
        cursor = bucket.find({"filename": {"$regex": f"^{prefix}\\d+$"}})
        best_seq = -1
        best_meta: dict | None = None
        async for grid_out in cursor:
            seq = int(str(grid_out.filename).rsplit("#", 1)[-1])
            if seq > best_seq:
                best_seq = seq
                best_meta = grid_out.metadata or {}
        return best_meta

    async def cleanup_stale_chunks(
        self, db: AsyncIOMotorDatabase, older_than: datetime
    ) -> int:
        """Delete GridFS chunk files whose interview was never finalized.

        A recording is "orphaned" when chunks exist in GridFS but the owning
        interview has no finalized `RecordingMeta` for that kind (e.g. the tab
        was closed before `finalize=true` was sent, or the interview was
        abandoned). Intended to be run periodically by a scheduled task or an
        admin endpoint. Returns the number of chunk files deleted.
        """
        bucket = self._bucket(db)
        # All recording chunk filenames look like "<interview_id>:<kind>#<seq>".
        cursor = bucket.find({"filename": {"$regex": "^[0-9a-f]{24}:(camera|screen)#\\d+$"}})
        deleted = 0
        async for grid_out in cursor:
            filename = str(grid_out.filename)
            interview_id, _, rest = filename.partition(":")
            kind = rest.rsplit("#", 1)[0]
            created = grid_out.upload_date
            if created is None or created >= older_than:
                continue
            doc = await self._interviews.get_by_id(db, interview_id)
            if doc is None:
                # Interview deleted — drop the chunks.
                try:
                    await bucket.delete(grid_out._id)
                    deleted += 1
                except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                    logger.warning("Failed to delete orphan chunk: %s", exc)
                continue
            interview = Interview(**doc)
            meta = interview.recordings.get(kind)
            if meta is not None and meta.finalized:
                continue
            # Chunks exist but recording never finalized and is old enough.
            try:
                await bucket.delete(grid_out._id)
                deleted += 1
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                logger.warning("Failed to delete stale chunk: %s", exc)
        return deleted


recording_service = RecordingService(interview_repository)
