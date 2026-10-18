"""Session recording storage: chunked GridFS upload and streamed download.

Interviews record a single camera composite (screen base layer + camera PiP +
mic audio) as webm. The frontend records with `MediaRecorder(timeslice=...)` and
uploads each blob as a chunk; the first chunk (`seq=0`) resets any prior
incomplete upload, and `finalize=True` seals the file and writes `RecordingMeta`
onto the interview document. Bytes live in GridFS; only metadata is ever
returned in API JSON.
"""

import logging
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorGridFSBucket

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from app.models.interview import Interview, RecordingMeta
from app.repositories.interview_repository import InterviewRepository, interview_repository

logger = logging.getLogger(__name__)

RecordingKind = str  # "camera" (screen+camera composite) — validated by the API layer
ALLOWED_RECORDING_KINDS = ("camera",)
ALLOWED_RECORDING_CONTENT_TYPES = ("video/webm", "video/mp4", "video/x-matroska")


def _parse_datetime(value: object) -> datetime | None:
    """Parse a stored ISO timestamp, tolerating junk from old documents."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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
        capture_started_at: datetime | None = None,
    ) -> RecordingMeta | None:
        """Append one recorded chunk for (interview, kind).

        `seq=0` deletes any existing GridFS file for that kind and starts a
        fresh upload (crash-tolerant restart). The GridFS file's `metadata`
        tracks `seq` and running `size_bytes` so the total cap is enforced
        across chunks. `finalize=True` writes the sealed `RecordingMeta` to
        the interview document.

        ``capture_started_at`` (client-reported media-recorder start) is stored
        on the first chunk that supplies it and carried forward, so the sealed
        metadata can map answer timestamps onto positions in the recording.
        """
        if kind not in ALLOWED_RECORDING_KINDS:
            raise NotFoundError(f"Unknown recording kind: {kind}")
        # Normalize away codec/parameters (e.g. "video/webm;codecs=vp9,opus")
        # so MediaRecorder blobs validate against the bare MIME allow-list.
        base_content_type = content_type.split(";", 1)[0].strip().lower()
        if base_content_type not in ALLOWED_RECORDING_CONTENT_TYPES:
            raise UnsupportedMediaTypeError("Unsupported recording content type.")
        content_type = base_content_type
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
        # First non-null capture start wins and is carried forward on every
        # chunk, so the highest-seq chunk always exposes it to `_seal`.
        prev_started = (existing_meta or {}).get("capture_started_at")
        capture_iso = (
            capture_started_at.isoformat() if capture_started_at is not None else prev_started
        )

        # GridFS has no append, so each chunk is its own file, named
        # "<interview>:<kind>#<seq>" and concatenated on read.
        chunk_filename = f"{file_id}#{seq}"
        grid_in = bucket.open_upload_stream(
            chunk_filename,
            metadata={
                "interview_id": interview_id,
                "kind": kind,
                "seq": seq,
                # Running total, not this chunk's size — the next append reads
                # it back to enforce the cap across the whole recording.
                "size_bytes": total,
                "content_type": content_type,
                "capture_started_at": capture_iso,
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

        chunk_meta = await self._read_grid_meta(bucket, f"{interview_id}:{kind}")
        now = datetime.now(UTC)
        meta = RecordingMeta(
            file_id=f"{interview_id}:{kind}",
            content_type=content_type,
            size_bytes=total,
            chunk_count=count,
            finalized=True,
            capture_started_at=_parse_datetime((chunk_meta or {}).get("capture_started_at")),
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
            # GridOut.read() returns bytes synchronously in Motor.
            chunks[seq] = grid_out.read()
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

    async def purge_interview_recordings(
        self, db: AsyncIOMotorDatabase, interview_id: str
    ) -> int:
        """Delete every GridFS chunk for an interview, any kind (erasure).

        Owner-agnostic on purpose: it is only called by the retention/erasure
        path after access has already been authorized. Returns chunks deleted.
        """
        bucket = self._bucket(db)
        cursor = bucket.find({"filename": {"$regex": f"^{interview_id}:"}})
        deleted = 0
        async for grid_out in cursor:
            try:
                await bucket.delete(grid_out._id)
                deleted += 1
            except Exception as exc:
                logger.warning("Failed to erase recording chunk: %s", exc)
        return deleted

    async def recording_manifest(
        self, db: AsyncIOMotorDatabase, interview_id: str
    ) -> list[dict]:
        """Summarize the GridFS chunks stored for an interview, by kind.

        Owner-agnostic (metadata only, no bytes): used by the right-of-access
        export to report what recordings exist without reading them out.
        """
        bucket = self._bucket(db)
        cursor = bucket.find({"filename": {"$regex": f"^{interview_id}:"}})
        kinds: dict[str, dict] = {}
        async for grid_out in cursor:
            name = grid_out.filename or ""
            kind = name.split(":", 1)[1].split("#", 1)[0] if ":" in name else name
            row = kinds.setdefault(
                kind,
                {
                    "kind": kind,
                    "file_id": str(grid_out._id),
                    "content_type": "video/webm",
                    "size_bytes": 0,
                    "chunk_count": 0,
                    "created_at": grid_out.upload_date,
                },
            )
            row["size_bytes"] += grid_out.length or 0
            row["chunk_count"] += 1
            metadata = grid_out.metadata or {}
            if metadata.get("content_type"):
                row["content_type"] = metadata["content_type"]
        return list(kinds.values())

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
        # All recording chunk filenames look like "<interview_id>:camera#<seq>".
        cursor = bucket.find({"filename": {"$regex": "^[0-9a-f]{24}:camera#\\d+$"}})
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
