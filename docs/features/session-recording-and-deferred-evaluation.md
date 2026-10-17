# Session Recording & Deferred Evaluation

Feature specification for the AI Interview Coach mock-interview flow.

## 1. Goals

- **Silent session recording.** Camera, microphone, and screen share are captured during the interview and persisted for post-exam playback. The in-session Candidate panel shows a live self-view (screen base layer + camera PiP) alongside recording status; capture itself is silent and never blocks the session.
- **Scoring happens only at exam end.** During the session the AI only asks questions and the candidate only answers. Live scoring, AI feedback, and per-answer evaluation are removed from the in-progress workspace.
- **Everything is reviewable after the exam.** The result page shows the recording, per-answer evaluations (scores, strengths, weaknesses, coach feedback, improved answer), and the aggregate report.

## 2. UX Flow

### 2.1 Start (unchanged, plus recording start)
1. Waiting room: proctoring consent checkbox → Start.
2. Device check: camera + screen-share previews with status pills → Next.
3. Interview starts → recorder hook starts capturing (screen base layer, camera PiP, mic audio). Candidate panel shows a live self-view plus recording status.

### 2.2 In-session (simplified)
1. AI interviewer asks a question (TTS auto-plays).
2. Candidate answers by typing or voice (STT).
3. Submit → answer stored → next question generated → appended to conversation → TTS auto-plays. No evaluation, no score panels, no manual "Next question" click.
4. Candidate panel: live self-view (screen share base with a camera PiP, or camera-only, or an avatar placeholder) + pulsing red "Recording" indicator + elapsed time + cam/mic/screen status pills + control buttons (mic, camera, screen, leave).
5. Controls still toggle tracks mid-session; toggles also emit proctoring events.

### 2.3 Completion
1. Final answer submitted → interview marked `completed` immediately (no evaluation in the response path).
2. Recorder stops → chunks are already uploaded (chunked pipeline) → finalize call seals metadata → frontend shows "Saving your session…" → navigates to result page.
3. Background task evaluates all answers in parallel and generates the report. If it fails, the report endpoint backfills on first access.

### 2.4 Result page
1. Recording player: the camera composite video; blob fetched with auth, played via `URL.createObjectURL` (revoked on unmount).
2. Answer review: per-question card with question, candidate answer, 5-dimension score bars, strengths, weaknesses, coach feedback, improved answer.
3. Aggregate report: overall/technical/communication scores, narrative, strong/weak topics, preparation plan.
4. Report loading: poll `GET /report` every 3s with an "Analyzing your answers…" state; after ~3 minutes fall back to a manual "Try again" button (never a single hung 120s request).

## 3. Data Model

### 3.1 Answer (evaluation deferred)
```python
class Answer(BaseModel):
    id: str
    question_id: str
    text: str
    evaluation: Evaluation | None = None   # None until end-of-exam evaluation
    created_at: datetime
```

### 3.2 Interview recording metadata
```python
class RecordingMeta(BaseModel):
    file_id: str            # GridFS file id
    content_type: str       # e.g. "video/webm"
    size_bytes: int
    chunk_count: int = 0
    finalized: bool = False
    created_at: datetime
    updated_at: datetime

class Interview(BaseModel):
    ...
    recordings: dict[str, RecordingMeta] = {}   # keyed by kind: "camera" (composite)
```

### 3.3 Storage
- **GridFS** bucket `interview_recordings` (MongoDB). One logical file per (interview, kind). Chunks appended via `AsyncIOMotorGridFSBucket` (`open_upload_stream` / re-upload replace semantics).
- Rationale: single persistence layer, no path-traversal surface, backup = Mongo dump, matches the "save in database" requirement.

## 4. API Contract

### 4.1 Answer submission (modified)
`POST /api/questions/{question_id}/answer`
- Request: `{ "answer": "..." }` (unchanged)
- Response: `AnswerResultOut`
  - `evaluation: Evaluation | None` — **always `None` during the session**
  - `next_question`, `status`, `questions_answered`, `target_questions` (unchanged)
  - On the final answer: `status: "completed"`, `next_question: null`, `evaluation: null`
- Behavior: one LLM call (next-question generation) except on the final answer (zero LLM calls in the request path). Evaluation is deferred to a background task.

### 4.2 Report (modified)
`GET /api/interviews/{id}/report`
- Unchanged contract (`ReportOut`).
- New behavior: if any answer lacks an evaluation, backfill them (bounded-parallel, per-interview `asyncio.Lock`) before generating the report. This is the safety net for background-task failure.

### 4.3 Recording upload (new)
`POST /api/interviews/{id}/recordings/chunk`
- Multipart form: `kind` (`camera` — the only supported kind), `seq` (int, chunk index, 0-based), `chunk` (file part), `finalize` (bool, optional).
- Appends the chunk to the GridFS logical file for (interview, kind). First chunk (`seq=0`) resets any previous incomplete upload for that kind.
- `finalize=true`: seals the file, writes `RecordingMeta` (`finalized: true`, `size_bytes`, `chunk_count`) onto the interview document.
- Guards: ownership check, per-chunk size cap, total size cap (~500MB), content-type validation (`video/webm`), rate-limited.
- Response: `204 No Content` on success.

`GET /api/interviews/{id}/recordings/{kind}`
- Ownership check → stream the GridFS file with the stored `Content-Type` and `Content-Length`.
- 404 if the kind is absent or not finalized.
- Frontend fetches with the Bearer header (axios) and plays via object URL.

### 4.4 Interview detail (modified)
`GET /api/interviews/{id}`
- `recordings` metadata included (kinds present only, no bytes).
- `answers[].evaluation` may be `null` for completed interviews whose background evaluation has not finished; clients should treat missing evaluation as "pending".

### 4.5 Proctoring events (new)
`POST /api/interviews/{id}/proctoring/events`
- Request: `{ "type": "camera_off", "details": { ... } }` — types emitted by the client: `camera_on`/`camera_off`, `mic_on`/`mic_off`, `screen_on`/`screen_off`.
- Appends a `ProctoringEvent` to `proctoring_session.events` via a race-safe `$push` (concurrent track toggles cannot clobber each other).
- Only accepted while the interview is `in_progress` or `completed` (409 otherwise); rate-limited with the recording-upload budget.
- Response: `204 No Content`.

## 5. Client Capture & Composite

### 5.1 Composite (single recording, synced)
- `<canvas>` compositor: screen stream as base layer, camera stream drawn as a PiP overlay (bottom-right corner), mic audio attached.
- Output: `canvas.captureStream()` + audio track → one `MediaRecorder` → one webm file stored under kind `camera`. The composite already contains the screen, so no separate `screen` kind is produced or stored.
- Fallback: if `captureStream` is unsupported, record the raw camera stream (video + audio) only.

### 5.2 Chunked upload (crash-tolerant)
- `MediaRecorder.start(timeslice = 10_000)` — every ~10s a `dataavailable` blob is produced.
- Each blob is uploaded as a chunk (`seq` incremented). Upload failures are retried once, then logged; the session continues (upload is best-effort, never blocks the interview).
- On completion or explicit leave: stop the recorder → flush the final blob → send `finalize=true`.
- Maximum session recording length enforced client-side: `min(target_questions * 4 min, 25 min)` → auto-finalize and stop the recorder.

### 5.3 Events
- `screen_share_stopped`, `camera_disabled`, `mic_muted` (and enable counterparts) are appended to `ProctoringSession.events` (existing model) at the moment they occur — cheap now, backbone of integrity flagging later.

## 6. Backend Evaluation Pipeline (deferred)

### 6.1 Request path (hot)
- `answer_question`: store answer (`evaluation=None`) → generate next question with the **eval-free prompt variant** (the interviewer model decides follow-up / harder / easier / new-topic from the previous question + answer text alone) → on final answer mark completed.
- No evaluation LLM call in the request path.

### 6.2 Background task (on completion)
- Spawned via `asyncio.create_task` (strong reference set to prevent GC).
- For each answer missing an evaluation, run the existing `EVALUATE_ANSWER_PROMPT` under a bounded semaphore (3–5 concurrent).
- **Incremental persistence**: each evaluation is written to its answer the moment it finishes (`$set` with `arrayFilters` on `answers.$[el].id`) — a crash mid-run keeps completed work.
- After all evaluations persist, generate and cache the report (existing `GENERATE_REPORT_PROMPT` + `aggregate_scores`).

### 6.3 Report backfill (safety net)
- `report()` acquires a per-interview `asyncio.Lock`.
- If any answer is still unevaluated, backfill (same bounded-parallel path) then generate/cache the report.
- `aggregate_scores` / `_performance_payload` defensively skip `evaluation is None` so report generation never crashes on partial data.

## 7. Failure Modes & Trade-offs (accepted this iteration)

| Risk | Mitigation / acceptance |
|---|---|
| Tab closed mid-session | Chunked upload means at most the last ~10s is lost (vs. the whole recording with end-only upload). |
| Background evaluation task dies | Report endpoint backfills on access; incremental writes keep completed evaluations. |
| Large recording memory | Chunks uploaded as produced; backend streams into GridFS; playback downloads the blob (no Range/seek streaming yet — acceptable for typical session lengths). |
| `captureStream` unsupported | Fallback to raw camera-only recording. |
| Duplicate evaluation under races | Per-interview lock on report backfill; background task and backfill share the same "evaluate if missing" guard. |
| Storage abuse | Per-chunk + total size caps, rate-limited upload, ownership checks on every endpoint. |

## 8. Phased Implementation Checklist

### Phase 1 — Backend: deferred evaluation
- [x] `Answer.evaluation` optional (`None` default); `AnswerResultOut.evaluation` optional
- [x] Eval-free next-question prompt variant (no `feedback` / `decision` inputs)
- [x] `answer_question` removes per-answer evaluation; stores answer + next question; marks completion without scoring
- [x] Background task: bounded-parallel evaluation, incremental per-answer writes, then report generation
- [x] `report()` per-interview lock + synchronous backfill of missing evaluations
- [x] `aggregate_scores` / `_performance_payload` guard `None` evaluations
- [ ] Verify: import checks, uvicorn reload, curl answer → fast response, final answer → completed, `GET /report` returns full report

### Phase 2 — Backend: recording storage
- [x] `RecordingMeta` + `Interview.recordings` model/schema; exposed on `InterviewOut`
- [x] `POST /{id}/recordings/chunk` (append, upsert-per-kind, finalize) with ownership, size caps, content-type validation, rate limit
- [x] `GET /{id}/recordings/{kind}` ownership-checked stream with correct content-type
- [x] Orphan GridFS cleanup on re-upload/replace
- [ ] Verify: curl chunked upload → download byte-identical; 403 for non-owner (needs live Mongo)

### Phase 3 — Frontend: capture & composite
- [x] Canvas compositor (screen base + camera PiP + mic audio; fallback to camera-only)
- [x] `use-interview-recorder` hook: 10s timeslice, chunked upload, finalize, length cap, state machine (`idle | recording | uploading | uploaded | error`)
- [x] Services: `uploadRecordingChunk`, `getRecordingBlob`, `recordingKinds`
- [x] Types: optional `evaluation`, `RecordingMeta`, `InterviewDetail.recordings`
- [x] Verify: `npm run typecheck` clean

### Phase 4 — Frontend: in-session UX
- [x] Remove `LiveScore`, `AIFeedback`, `EvaluationCard` and all evaluation/feedback/metrics state from the workspace page
- [x] Candidate panel: live self-view (screen base + camera PiP, camera-only, or avatar placeholder) + recording indicator + elapsed + status pills + controls
- [x] Auto-advance: submit → next question appended → TTS auto-play
- [x] Completion / End Interview → stop recorder → "Saving your session…" → upload → navigate
- [x] Proctoring events on track toggles (`camera_on/off`, `mic_on/off`, `screen_on/off` via `POST /proctoring/events`)
- [x] Busy text: "AI is preparing the next question…"; waiting-room copy updated
- [x] Verify: typecheck; manual session with no scoring UI

### Phase 5 — Frontend: result page
- [x] Recording player (blob → objectURL, revoked on unmount; single composite recording)
- [x] Answer review section (per question: text, answer, score bars, strengths, weaknesses, feedback, improved answer)
- [x] Report polling (3s interval, ~3min cap, manual retry fallback)
- [x] Verify: typecheck; end-to-end complete → result shows recording + review + report

### Phase 6 — Hardening
- [x] Ownership / size-cap / rate-limit audit on new endpoints (fixed dict-vs-model access bug in `read_recording`; added per-scope rate-limit overrides so `recording_upload` gets 60/min)
- [x] Orphan cleanup (`RecordingService.cleanup_stale_chunks` for abandoned/never-finalized recordings) + length cap enforced (config + client auto-finalize)
- [x] Full `npm run typecheck` + backend import checks
- [ ] Curl round-trips (chunked upload → download byte-identical; 403 for non-owner) — **blocked: MongoDB not reachable**
- [x] Doc updated with final API contract and any deviations

## 9. Verification Commands

```bash
# Frontend (must stay clean after every change)
cd frontend && npm run typecheck

# Backend syntax/import check
cd backend && py -c "import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('app').rglob('*.py')]"

# Dev servers (already running)
# frontend: http://localhost:3000
# backend:  uvicorn --reload --port 8000
```
  