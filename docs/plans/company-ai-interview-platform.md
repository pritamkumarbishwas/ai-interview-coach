# Company AI Interview Platform — Product & Delivery Plan

> **Status:** Draft for review
> **Owner:** Product / Engineering
> **Last updated:** 2026-10-18

This document plans the evolution of the current single-user, candidate-facing
 **AI Interview Coach** into a **company-facing platform for first-round AI
 interviews**. It is the source of truth for scope decisions; implementation
 instructions live in separate tickets derived from this plan.

---

## 1. Vision

> **"Structured, proctored AI screening in a link."**

A recruiter attaches an interview template to a job requisition, invites
candidates by link, candidates complete a standardized, proctored AI interview
with **zero sign-up friction**, and the recruiter receives a **ranked,
evidence-backed shortlist** with integrity signals — consistent, fast, and
bias-aware.

### Locked decisions

| Decision | Choice |
| --- | --- |
| Deployment | **Single-company** (one install per customer) — **no** multi-tenant `org_id` |
| Candidate access | **Magic link, no account** |
| Candidate entry friction | Token-gated session; candidates are guests, not `User` records |
| Interview rounds | Voice + typed **+ coding editor + whiteboard** (full target) |
| Interviewer | **Fully AI** first round; humans review and decide |
| ATS / SSO | **Later** (not in MVP) |
| Existing candidate practice flow | **Kept as a separate optional module** |
| First shippable MVP | Phases 1–4 + 6 + minimal 5 & 7 |

### Non-goals (for the MVP)

Multi-tenant SaaS isolation, ATS/SSO integrations, billing, billing seats,
face-recognition proctoring, code *execution*, live human interviewer in-session.

---

## 2. Personas & roles

A single company install has internal **staff users** (role-based) and
**candidates** (invitation guests, no account).

| Persona | Type | Role / access |
| --- | --- | --- |
| Admin | Staff user | Manage team, templates, jobs, settings, retention |
| Recruiter | Staff user | Create jobs, invite candidates, review, decide |
| Reviewer | Staff user | Score/comment on assigned candidates (may be hiring manager) |
| Candidate | Guest (invitation token) | Complete one assigned interview; see nothing else |
| Candidate (practice) | Existing user | Optional module: self-serve practice with account login |

Public self-registration is **disabled** in a screening deployment; staff are
created by admin invite.

---

## 3. Current state (reusable assets)

| Area | Current implementation | Reuse |
| --- | --- | --- |
| Auth | JWT + Argon2, no roles (`app/models/user.py`) | Extend with roles + magic-link path |
| Interview engine | Adaptive questions, LLM + RAG (`app/services/interview_service.py`, `rag_service.py`) | Reuse for screening rounds via `kind` discriminator |
| Recording | Chunked GridFS composite video (camera+screen+mic) + playback | Reuse as evidence; add retention/compression |
| Proctoring | Consent + on/off events (`app/models/interview.py:39-51`) | Wire existing fields + add scoring |
| Evaluation | Deferred per-answer eval + aggregate `Report` | Extend into competency rubric scorecards |
| Frontend | Candidate workspace, device check, recorder, candidate panel (with live previews), result page | Reuse candidate side; build recruiter side |
| Ops | Rate limiting, error envelope, structured logging, body-size guard | Reuse; add per-token limits + mailer + job runner |

### Key structural constraints discovered

- **Everything is user-scoped.** Every endpoint in `app/api/interviews.py` uses
  `get_current_user` and passes `current_user.id` into the service. A second
  auth path (`get_invitation_session`) is required for magic-link candidates,
  and each endpoint must split into recruiter (user-auth) vs candidate
  (token-auth) surfaces.
- **`ProctoringSession.started_at` / `ended_at` / `status` exist but are never
  written** (`app/models/interview.py:46-51`); only `consent_given_at` is set.
- **`proctoring_mode` ("off" / "camera_only" / "strict") already exists** on the
  interview — reusable as template strictness.
- **MongoDB 16 MB document limit risk.** `Interview` embeds `questions`,
  `answers`, `report`, `recordings`, and `proctoring.events`. Transcripts +
  integrity timelines will push this limit.
- **STT fragility.** Web Speech API is `en-US` only and unsupported in
  Firefox/Safari; unreliable for a hiring product.

---

## 4. Gap analysis

| Area | Missing today | Why it matters |
| --- | --- | --- |
| Roles & access | Roles, staff invites, role guards | Staff vs candidate; least privilege |
| Candidate access | Magic-link invites, guest sessions | Zero-friction completion |
| Requisitions | Jobs/openings, rounds, pipeline | Recruiters think in requisitions |
| Templates | Template builder, question bank, competency rubric | Standardization & consistency |
| Scheduling | Deadlines/windows, reminders, server-authoritative timing | Integrity + operations |
| Integrity | Presence/tab/screen signals, integrity score, timeline | Anti-cheat is the core value |
| Scoring | Competency rubric, evidence citations, calibration | Defensible hiring decisions |
| Review workspace | Ranked shortlist, scorecards, compare, decisions, audit | Recruiter daily driver |
| Notifications | Email/reminder service | Invites/reminders need a mailer |
| Async jobs | Background worker | End-of-exam evaluation at scale |
| Compliance | Retention/erasure, audit, PII handling, accommodations | Legal blocker for HR buyers |

---

## 5. MVP definition

**MVP = Phase 0 (prereqs) + Phases 1, 2, 3, 4, 6, minimal 5 & 7.**

A sellable pilot: create a job → attach a template → invite via magic link →
candidate completes a proctored voice/typed AI interview → competency scorecard
with evidence → recruiter reviews a ranked shortlist with advisory integrity
flags and decides.

**Deferred past MVP:** code *execution*, whiteboard, face/ML proctoring,
analytics, exports, ATS/webhooks, SSO/SAML, billing.

**Delivery approach:** build one **thin vertical slice** (one screening interview
end-to-end) behind the existing engine first, to de-risk, then broaden.

---

## 6. Phase-wise roadmap

Effort: **S** ≈ 1 week, **M** ≈ 2–3 weeks, **L** ≈ 4–6 weeks, **XL** ≈ 6+ weeks
(single senior full-stack; adjust to team size).

### Phase 0 — Prerequisites (M) — *new, mandatory before Phase 1*
**Goal:** make the refactor safe and unblock later phases.
**Deliverables**
- Runnable backend test DB (local Mongo / `mongomock` / testcontainers) so the
  existing pytest suite actually runs; fix `.env` dependency on unreachable
  Atlas SRV.
- Mailer abstraction + basic email templates (provider-agnostic).
- Background job runner (persistent queue) for evaluation/reminders.
- Feature-flag / template-config scaffolding.
**Exit criteria:** `pytest` green locally; a test email sends; a background job
runs and survives restart.

### Phase 1 — Roles & access foundation (L)
**Goal:** internal staff with roles; candidates are guests.
**Deliverables**
- `User.role` (`admin`/`recruiter`/`reviewer`); staff invitation flow.
- Role guards on every endpoint; audit-log scaffold.
- Disable public self-registration (screening deployment).
- `Interview.kind` discriminator (`practice` | `screening`) so the practice
  module and screening coexist on one engine.
**Reuse:** existing JWT/Argon2 auth.
**Exit criteria:** role tests pass; practice module still works; screening
endpoints reject unprivileged users.

### Phase 2 — Jobs & interview templates (L)
**Goal:** recruiters define standardized rounds.
**Deliverables**
- `Job` (requisition) + `InterviewTemplate` (rounds, duration, difficulty,
  question bank / competency mapping, `proctoring_mode`, integrity policy).
- Template builder UI; DB-backed question bank grounded via RAG.
**Reuse:** `rag_service`, `llm_service`, existing `InterviewType`/`Difficulty`.
**Exit criteria:** create job → attach template → preview generated questions.

### Phase 3 — Candidate invitation & magic-link entry (L)
**Goal:** invite and start a session with no account.
**Deliverables**
- `Invitation` with **short-lived, single-use, interview-bound** tokens.
- `get_invitation_session` auth dependency; candidate-token endpoint surface.
- Scheduling: start window + **server-authoritative** `round_deadline`.
- Email invites + reminders; consent + device pre-check; optional resume/context.
- Per-token rate limits; `Cache-Control: private, no-store` on token responses.
**Reuse:** device check, consent flow.
**Exit criteria:** invite email → candidate completes pre-check and starts,
with no account; expired/used tokens rejected; server enforces the deadline.

### Phase 4 — Candidate AI interview panel (L-UI/UX)
**Goal:** a resilient, accessible, low-friction proctored session.
**Deliverables**
- Per-question pacing/timer (display) + server-enforced time; save & resume.
- **Server-side STT** (replaces browser Web Speech) for accuracy + multilingual.
- Transcript panel; accessibility (captions, screen reader, keyboard) and
  **accommodation** paths (time extensions).
- Clear recording/proctoring notice; live self-view (already built);
  **passive integrity signals** (tab/blur, camera/mic on-off, screen-share
  state, copy/paste, devtools) captured as advisory events.
- Graceful failure recovery / retry.
**Reuse:** `candidate-panel.tsx`, `use-interview-recorder.ts`, GridFS recording.
**Exit criteria:** session completes on Chromium/Firefox/Safari; timer is
server-enforced; passive signals are recorded; no scores shown to candidate.

### Phase 5 — Proctoring & integrity engine (L) — *minimal in MVP*
**Goal:** surface advisory integrity signals (no auto-reject).
**Deliverables**
- Wire existing `ProctoringSession.started_at/ended_at/status` lifecycle.
- `IntegrityReport`: aggregated passive signals + **advisory** integrity score
  + flagged-moments timeline with jump-to-moment evidence.
**Deferred:** face presence, multi-person detection, ML cheating detection.
**Exit criteria:** review shows an integrity summary + timeline; humans decide.

### Phase 6 — Evaluation & scoring engine (L)
**Goal:** consistent, evidence-backed, defensible scores.
**Deliverables**
- Competency rubric scoring with **structured output + answer evidence quotes**.
- Per-round score; cross-candidate **normalization**; **calibration mode** with
  a golden-set harness; **advisory** scores (human final).
- Bias guardrails: identity hidden until decision; rubric-only scoring.
**Reuse:** existing deferred `Report` → extend, keeping backward compatibility.
**Exit criteria:** golden-set calibration is stable; every score cites evidence.

### Phase 7 — Recruiter review workspace (L) — *minimal in MVP*
**Goal:** decide in one screen.
**Deliverables**
- Job pipeline; ranked shortlist with filters/saved views.
- Scorecards; side-by-side compare; transcript ↔ recording timeline
  (jump-to-moment); integrity badges.
- Decision workflow (advance/hold/reject), notes/@mentions, full audit trail.
**Exit criteria:** a reviewer can triage and decide a candidate without leaving
the workspace.

### Phase 8 — Analytics, exports & integrations (L) — *post-MVP*
Funnel/pass-rate/score distributions, CSV/PDF export, ATS webhooks
(Greenhouse/Lever first), public API keys.
> **Status: implemented.** `GET /api/invitations/analytics` and `/export` (CSV),
> `/export.pdf`; `api_keys` collection + `X-API-Key` auth and read-only
> `/api/public/*` surface; per-job signed outbound ATS webhooks delivered via the
> background queue. Provider payload blocks need validation against each
> partner's live API before go-live.

### Phase 9 — Compliance, security & billing (L) — *post-MVP*
Retention & erasure, DPA/data-processing, region residency, encryption at rest,
SSO/SAML, per-role limits, LLM cost tracking, seats/credits billing.
> **Status: all code-implementable items done.**
> Retention & erasure (`POST /api/invitations/{id}/erase`,
> `POST /api/invitations/retention/purge`, `retention.purge` job); data-subject
> access (`GET /api/invitations/{id}/data`); encryption at rest for app-managed
> secrets (`FIELD_ENCRYPTION_KEY`); per-role daily quotas (`ROLE_LIMITS`,
> 429 + `GET /api/usage/quotas`); seats and spend caps (`MAX_STAFF_SEATS`,
> `MONTHLY_LLM_BUDGET_USD`); LLM cost tracking (`llm_usage` +
> `GET /api/usage/summary`); residency/data-processing record
> (`GET /api/compliance` + `docs/compliance/data-processing.md`). Remaining and
> **deliberately not stubbed**: SSO/SAML (needs an external IdP) and paid billing
> (needs a payment vendor); see the data-processing doc's "Not yet shipped".

### Phase 10 — Advanced AI (ongoing) — *post-MVP*
Shadow mode (AI vs human panel agreement), explain-answer assist, cheating ML,
sentiment/communication analytics, role simulations, model routing/cost
optimization, code execution sandbox, whiteboard.
> **Status: first slice shipped — shadow mode.**
> `GET /api/invitations/shadow?job_id=` compares the advisory AI recommendation
> (`meets_threshold`) against the human decision actually recorded (`advance` vs
> `hold`/`decline`) and reports the agreement rate, a 2×2 agreement grid, each
> side's advance rate and a leniency verdict — plus the bounded disagreements
> and the exclusion counts (no threshold / no decision / not completed), so a
> small sample is never read as agreement. It is a pure function over the
> shortlist pipeline (`app/services/shadow_service.py`, `app/models/shadow.py`)
> and is surfaced in the job page's "Shadow mode" panel. Remaining: explain-answer
> assist, sentiment/communication analytics, model routing/cost optimization,
> role simulations, and the not-yet-started big-ticket items (cheating ML, code
> execution sandbox, whiteboard).

---

## 7. Data model changes

- `User`: add `role`.
- `Interview`: add `kind` (`practice` | `screening`). Screening interviews are
  **invitation-owned**, not `user_id`-owned.
- New collections: `Invitation`, `Job`, `InterviewTemplate`, `Scorecard`,
  `IntegrityReport`, `AuditEvent`.
- **Split heavy child data out of `Interview`** (to avoid the 16 MB limit):
  `answers`, `transcript`, `proctoring_events`, `scorecards` keyed by
  `interview_id`.
- Repurpose existing `ProctoringSession` (`started_at`/`ended_at`/`status`) and
  `proctoring_mode`.
- `Report` → extended competency rubric shape (keep old fields readable).

---

## 8. UX specifications

### Candidate experience
- Zero-signup magic link; clear "recorded & proctored" notice.
- Calm, distraction-free; explicit progress + display timer.
- **No scores shown** during or after (unless opt-in feedback).
- Live self-view; integrity status at a glance.
- Auto-save/resume; graceful failure/retry; mobile-friendly.
- Accessibility: captions, screen reader, keyboard, **accommodations** (time
  extensions) for timed rounds.

### Recruiter experience
- Pipeline dashboard; ranked shortlist with filters/saved views.
- Evidence-first scorecards; transcript synced to video (jump-to-moment).
- Side-by-side compare; confidence + integrity badges.
- Decision + comment workflow; full audit trail.
- Bias guardrails: identity hidden until decision.
- Candidate transparency: AI screens, human decides.

---

## 9. Architecture & non-functional notes

- **Two auth paths:** staff (JWT user) and candidate (`get_invitation_session`
  token). Endpoints split accordingly.
- **Server-authoritative timing** for all deadlines/time limits.
- **Background jobs** for evaluation, reminders, exports.
- **Server-side STT** for accuracy and multilingual support.
- **Observability:** per-role metrics, LLM cost/usage.
- **Storage:** per-template retention windows, compression, store transcript +
  key clips; auto-expiry.

---

## 10. Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Refactor without runnable tests | Phase 0 test DB is mandatory |
| Magic-link token leakage | Single-use, short-lived, bound tokens; per-token rate limits; no-store caching; audit |
| Proctoring false positives | Passive signals only, **advisory**, human-in-the-loop; no auto-reject |
| AI scoring noise / bias | Fixed rubric, structured output, evidence quotes, golden-set calibration, advisory scores, identity hidden |
| LLM + video cost | Per-template caps, retention, compression, cost tracking |
| MongoDB 16 MB limit | Move child data to separate collections |
| Browser incompatibility | Server-side STT; explicit support matrix |
| Compliance / legal | Retention/erasure, DPA, accommodations, candidate transparency; obtain legal review |

---

## 11. Open decisions

1. Coding/whiteboard: own dedicated phase (recommended) vs. behind template
   flags — and whether code *execution* is ever in scope.
2. Email provider for the mailer abstraction.
3. Async job runner technology (e.g., in-process + Mongo-backed queue vs. Redis/
   Celery/RQ).
4. Server-side STT engine/hosting choice.
5. Retention defaults per template.
6. Whether rejected candidates receive opt-in AI feedback by default.
