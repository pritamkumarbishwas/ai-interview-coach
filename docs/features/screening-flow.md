# Screening flow

This document describes the recruiter-led screening product: how a requisition
becomes a candidate invitation, how the guest interview runs, and how a human
decision is recorded.

## Actors

| Actor | Account | Access |
|---|---|---|
| Candidate | None; guest identified by the invitation token | Only their own session |
| Recruiter | Staff user, role `recruiter` | Owns and manages their requisitions |
| Reviewer | Staff user, role `reviewer` | Read/decide on assigned requisitions |
| Admin | Staff user, role `admin` | Cross-owner override; mutations audited |

Screening candidates never get a `User` row. The invitation carries a
`guest_user_id` that is used as the interview owner. Candidate access is derived
from the token, not from a login.

## Requisition setup

1. A recruiter creates a job (`POST /api/jobs`) with a title, description, and
   optional template.
2. A template can define rounds, interview type, difficulty, duration, target
   question count, response modes, proctoring mode, rubric, and pass threshold.
3. An admin provisions staff (`POST /api/staff/invitations`); recruiters assign
   reviewers (`PUT /api/jobs/{id}/reviewers`).

A requisition is readable by its owner, any admin, or an assigned reviewer.
Only the owner or an admin may edit it, invite candidates, revoke/extend
invitations, or change reviewer assignments. Non-owners receive `404` so the
existence of another owner's requisition is not leaked.

## Invitation lifecycle

```text
pending ──start──> started ──complete──> completed
   │                  │
   ├──expire──────────┴──> expired
   └──revoke────────────> revoked
```

- Creating an invitation returns `accept_url`:
  `{FRONTEND_URL}/interview/{raw_token}`.
- Only a SHA-256 hash of the token is stored. Treat the raw link as a credential.
- The default lifetime is `INVITATION_TTL_DAYS` (7 by default) and can be
  overridden per invitation.
- A reminder rotates/returns a usable link; extend moves the expiry and deadline;
  revoke makes the token unusable.
- The link is resumable: it is not single-use. It remains usable until it
  expires, is revoked, or the interview is completed.

## Candidate session

1. `GET /api/screening/{token}` returns the pre-check data: role, company,
   interview type, difficulty, question count, proctoring mode, expiry, and
   start/round windows.
2. `POST /api/screening/{token}/start` creates the guest interview and a
   server-side `round_deadline`. Consent is required when proctoring is not
   `off`. Starting is idempotent: refreshing resumes the existing session.
3. `GET /api/screening/{token}/current-question` returns the current question
   and enforces the deadline.
4. `POST /api/screening/{token}/questions/{question_id}/answer` submits an answer,
   evaluates it, generates the next question, and enforces the deadline.
5. When the target question count is reached, the interview is marked
   `completed` and the invitation follows.
6. The browser uploads recording chunks to
   `POST /api/screening/{token}/recordings/chunk`; recording uploads are not
   blocked by the deadline so the last chunk is retained.
7. Advisory integrity events go to `POST /api/screening/{token}/proctoring/events`.
8. Optional server-side transcription uses `POST /api/screening/{token}/transcribe`.
   With `TRANSCRIPTION_PROVIDER=none`, the browser Web Speech API is the only
   speech-to-text path.

The start window (`start_window_start` / `start_window_end`) is checked when the
session starts. The round deadline is checked on current-question, answer,
transcription, and the screening deadline path. The frontend countdown is
display-only; the API is authoritative.

## Recording and integrity

- Recordings are stored as chunks in GridFS under `RECORDING_BUCKET_NAME`.
- Per-chunk and total-size limits are configured by
  `MAX_RECORDING_CHUNK_BYTES` and `MAX_RECORDING_BYTES`.
- Integrity signals are advisory. The integrity report includes a clean-session
  score, signal list, and recording availability.
- A human always makes the hiring decision. The UI labels AI output as advisory.

## Review and decision

Recruiters and assigned reviewers can load:

- `GET /api/invitations/{id}/scorecard` — stored evaluation aggregates
- `GET /api/invitations/{id}/integrity` — advisory signals and recording info
- `GET /api/invitations/{id}/timeline` — recording/integrity timeline
- `GET /api/invitations/{id}/recordings/{kind}` — recording stream
- `GET /api/invitations/shortlist?job_id=...` — advisory ranking
- `GET /api/invitations/analytics?job_id=...` — funnel and score distribution
- `GET /api/invitations/shadow?job_id=...` — advisory vs recorded decisions

`PATCH /api/invitations/{id}/decision` records `advance`, `hold`, `reject`, or
`pending` (clears a decision) with a note and actor. A decision is never set by
the AI. Decision changes are audited; cross-owner decisions record
`cross_owner=true`.

If the job has an enabled webhook, a `candidate.decided` job is queued. Delivery
requires a running background worker (`JOBS_ENABLED=true`); otherwise the job
stays queued in MongoDB.

## Privacy and retention

- `GET /api/invitations/{id}/data` exports candidate session data.
- `POST /api/invitations/{id}/erase` erases one candidate's session data.
- `POST /api/invitations/retention/purge` purges data older than
  `DATA_RETENTION_DAYS` and anonymizes invitation rows so aggregate analytics
  survive.
- The purge endpoint is gated by `RETENTION_PURGE_ENABLED`. No scheduler
  enqueues it automatically; trigger it from an admin/cron process if automatic
  retention is required.
- Webhook signing secrets can be encrypted at rest with `FIELD_ENCRYPTION_KEY`.

## Email delivery

The only built-in mail provider is `console`, which logs the message instead of
sending it. Invitation and reminder API responses still return `accept_url`, and
the recruiting UI displays it for copying. There is no SMTP/SES transport yet.

## Related files

- `backend/app/api/screening.py` — recruiter and public screening routes
- `backend/app/services/screening_service.py` — lifecycle and review orchestration
- `backend/app/services/scorecard_service.py` — advisory scorecard aggregation
- `backend/app/services/integrity_service.py` — advisory clean-session scoring
- `backend/app/services/retention_service.py` — erasure and purge
- `backend/app/core/handlers.py` — webhook and retention job handlers
- `docs/features/job-access-control.md` — access matrix and ownership rules
