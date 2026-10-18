# Job-Based Access Control

Feature specification for who may see and change requisitions (jobs), interview templates, and the screening pipeline built on top of them.

Implemented in commit `8844b9a` (*feat: implement job access control for owners, admins, and reviewers*) plus a follow-up commit `0c09cb3` fixing orphaned invitations and reviewer-facing copy. A quick summary also lives in the README under **Operational decisions → Job-based access control**.

## 1. Goals

- **Ownership stays the default.** Every requisition belongs to the recruiter who created it (`jobs.user_id`). A recruiter sees their own rows and nobody else's — guessing another owner's id yields a `404`, never a `403`, so existence never leaks.
- **Admins get a cross-owner override.** An admin can list, open, edit, and delete *any* owner's jobs and templates, and read or erase *any* invitation's candidate data. Every cross-owner mutation is written to the audit log with `metadata.cross_owner = true`.
- **Reviewers get a real read/decide role.** A reviewer is scoped to individual requisitions assigned to them (`jobs.reviewer_ids`). They can read the job, its candidates, scores, integrity, recordings, and pipeline analytics, and record a decision — but they cannot create, edit, or delete anything, nor invite/revoke/remind/extend candidates, erase or export a single candidate's PII, or change reviewer assignments.
- **No new tenancy model.** Single-tenant with role overrides — no `org_id`, no team scoping. The work is per-user ownership, not multi-org.

## 2. Roles

Roles are declared in `app/models/user.py`:

```python
Role = Literal["candidate", "admin", "recruiter", "reviewer"]
STAFF_ROLES: frozenset[str] = frozenset({"admin", "recruiter", "reviewer"})
```

| Role | Provisioned by | Intent |
|---|---|---|
| `candidate` | Self-registration (practice module) | Never touches recruiting surfaces |
| `recruiter` | Admin invitation (`/api/staff/invitations`) | Normal owner of jobs/templates/invitations |
| `reviewer` | Admin invitation | Read/decide on explicitly assigned requisitions |
| `admin` | Admin invitation or `BOOTSTRAP_ADMIN_*` | Cross-owner override + staff provisioning |

Route guards are the dependency factories in `app/api/deps.py`:

- `require_staff` — `admin`, `recruiter`, `reviewer` (all staff)
- `require_recruiter` — `admin`, `recruiter` (assignment/managing actions)
- `require_admin` — `admin` (provisioning, audit, compliance, retention purge)
- `require_quota(action, guard)` — runs `guard` first, then consumes a usage unit

## 3. Ownership & Access Resolution

### 3.1 The requisition gate

`app/services/job_access.py` is the single source of truth for whether a user may touch a job:

```python
def can_access_job(job_doc, actor) -> bool:   # read:  owner ∨ admin ∨ assigned reviewer
def can_manage_job(job_doc, actor) -> bool:   # mutate: owner ∨ admin

async def find_accessible_job(db, jobs, job_id, actor) -> dict | None
async def find_manageable_job(db, jobs, job_id, actor) -> dict | None
```

Both return `None` for a missing/invalid id **or** a permitted-but-unauthorized access, so every call site converts `None` into a `404`. Rows are fetched by `find_owned_document(db, collection, id, owner_field="user_id")` first (owner shortcut), then, for admins or assigned reviewers, by id.

### 3.2 What each service uses

| Service helper | Gate | Used by |
|---|---|---|
| `JobService._require_accessible` | `find_accessible_job` | `GET /jobs/{id}` |
| `JobService._require_manageable` | `find_manageable_job` | `PATCH`, `DELETE`, `PUT /{id}/reviewers` |
| `JobService._require_template` | template `find_owned`, admin falls back to any | job create/update with `template_id` |
| `ScreeningService._require_job` | `find_accessible_job` | create/list invitations, shortlist, analytics, shadow, exports, PDF |
| `ScreeningService._require_invitation` | **creator of the invitation OR its job is accessible** | revoke, remind, extend, decide, integrity, scorecard, timeline, recording |
| `RetentionService._require_job_access` | **creator of the invitation OR its job is accessible** | erase candidate data, GDPR export |
| `TemplateService._require` | template `find_owned`, admin falls back to any | all template read/write |

### 3.3 Access matrix

`M` = manage (mutate), `R` = read, `D` = record a decision, `—` = denied (`403` on the route, `404` when id-scoped and unauthorized).

| Surface | reviewer (assigned) | recruiter (owner) | admin (any) | candidate |
|---|---|---|---|---|
| List/open jobs | R | R (own) | R (all) | — |
| Create/edit/delete jobs | — | M | M | — |
| Create/edit/delete templates | — | M (own) | M (any) | — |
| Assign reviewers (`PUT /jobs/{id}/reviewers`) | — | M | M | — |
| Create invitation | — | M | M | — |
| List candidates / shortlist / analytics / shadow | R | R | R | — |
| CSV + PDF pipeline export | R | R | R | — |
| Decision (`PATCH …/decision`) | D | D | D | — |
| Integrity / scorecard / timeline / recording | R | R | R | — |
| Revoke / remind / extend | — | M | M | — |
| Erase candidate / GDPR data export | — | M | M | — |
| API keys (`/api/api-keys`) | — | M | M | — |
| Team provisioning, audit log, compliance, retention purge | — | — | M | — |

Practice data (interviews, resumes, job descriptions) is **deliberately unchanged**: it stays per-user, so admins do not get oversight of candidates' practice sessions.

## 4. Data Model

```python
class Job(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    user_id: str                                    # owner
    reviewer_ids: list[str] = Field(default_factory=list)   # assigned reviewers
    ...
```

- `LIST_PROJECTION` on `JobRepository` carries `user_id` + `reviewer_ids` so list responses can show ownership/assignments.
- `JobOut` / `JobSummary` expose `owner_id` (nullable) and `reviewer_ids` for admin oversight and for the assignment UI. `ReviewerAssignment` is the write schema for the assignment endpoint.
- Existing documents without `reviewer_ids` deserialize through the model default (`[]`) — no migration required; `{"reviewer_ids": user_id}` simply matches nothing until assigned.
- `reviewer_ids` can only reference existing users whose `role == "reviewer"`; anything else is rejected (`422`) before the write.

## 5. API Contract

### 5.1 New endpoint

`PUT /api/jobs/{job_id}/reviewers` — guard: `require_recruiter`
- Request: `{ "reviewer_ids": ["<userId>", …] }` (`ReviewerAssignment`, defaults to `[]` = clear)
- Validates each id exists and has `role == "reviewer"` (`InvalidInputError` → `422`)
- Owner-or-admin only (`find_manageable_job`), then audits `job.reviewers_changed` with the new list
- Response: `JobOut`

`GET /api/staff/reviewers` — guard: `require_recruiter`
- Response: `list[UserOut]` of every `reviewer` account (name/email/id only — `password_hash` is never serialised by `UserOut`)

### 5.2 Guard changes on existing endpoints

| Endpoint | Guard |
|---|---|
| `GET /api/jobs`, `GET /api/jobs/{id}` | `require_staff` (reviewers included) |
| `POST /api/jobs`, `PATCH`, `DELETE`, `PUT …/reviewers` | `require_recruiter` |
| `GET /api/invitations` (list), `/shortlist`, `/analytics`, `/shadow`, `/export`, `/export.pdf` | `require_staff` |
| `PATCH /api/invitations/{id}/decision`, `/integrity`, `/scorecard`, `/timeline`, `/recordings/{kind}` | `require_staff` |
| `POST /api/invitations` (create), `DELETE` (revoke), `/remind`, `/extend` | `require_recruiter` |
| `POST /api/invitations/{id}/erase`, `GET /api/invitations/{id}/data` | `require_recruiter` |
| All `/api/templates` routes | `require_recruiter` |

### 5.3 Public ATS API stays owner-scoped

`app/api/public.py` authenticates with `X-API-Key` and builds a stand-in identity via `_owner(key)` that is **always `role="recruiter"`**, never the key creator's real role. Consequence: an admin's API key still resolves to owner-only access, so the public surface can never read across the tenant regardless of who minted the key.

## 6. Frontend

Role constants live in `frontend/lib/recruiting.ts`:

- `STAFF_ROLES = ["admin", "recruiter", "reviewer"]`
- `RECRUITING_ROLES = ["admin", "recruiter"]`
- `ADMIN_ROLES = ["admin"]`

| Route | Guard |
|---|---|
| `/jobs`, `/jobs/[id]` | `STAFF_ROLES` (reviewers may open assigned requisitions) |
| `/templates`, `/templates/[id]` | `RECRUITING_ROLES` |
| `/team`, `/audit` | `ADMIN_ROLES` |

Within `/jobs/[id]`, `canManage = user.role in {admin, recruiter}` drives cosmetics only — the server enforces the real policy:

- **Reviewer view:** read-only job card (`ReadOnlyJobDetails`), no invite form, no reminder/revoke/extend controls, no edit form / delete button, no **Reviewers** card. Decision dropdown, shortlist, integrity, scorecard, timeline, recording, analytics, shadow, and exports stay available.
- **Recruiter/admin view:** everything above plus the **Reviewers** card (`ReviewersPanel` → `GET /staff/reviewers` + `PUT /jobs/{id}/reviewers`) and the invite form.
- `/jobs` list: reviewers get "Requisitions you've been asked to review." + "No jobs assigned to you" empty state, no New-job button, no template chip (their template list is not fetched).
- Sidebar: `Templates` nav is restricted to `["admin", "recruiter"]` so it matches the page guard (reviewers no longer see a link that would redirect them).

Frontend hiding is never the security boundary — every one of these actions is independently rejected server-side.

## 7. Orphaned Invitations (the stranding rule)

Invitation access used to be keyed on `screening_invitations.created_by`. Moving it to job-based access made one case worse: deleting a requisition does **not** cascade to its invitations (the delete modal says "Invitations already sent are kept"), so job-derived access returned `404` for *everyone including the owner* — leaving candidate data that could no longer be revoked, decided, **erased**, or **exported** until the timed retention purge got to it.

Resolution — access is the **union** of the two rules:

```
access(invitation, actor) =
      invitation.created_by == actor.id
   OR job(invitation) is accessible to actor (owner ∨ admin ∨ assigned reviewer)
```

Applied in `ScreeningService._require_invitation` and `RetentionService._require_job_access`.

Why this is safe rather than a regression back to the old rule:

- Reviewers can never *create* invitations (`require_recruiter`), so `created_by` can never be a reviewer id — the creator fallback cannot smuggle a reviewer into a decision/erase path they weren't assigned.
- Job-derived access is the path an *admin* uses to manage invitations the *owner* created, and the creator path is what an owner uses after their job disappears. Neither substitutes for the other, so the admin-stranding problem that motivated job-based access remains fixed.
- An invitation creator who is not the job owner still gets a `404` for job-scoped reads (`GET /invitations?job_id=…`, shortlist, analytics) when the job is gone.

### Known limitation

Orphaned invitations are reachable **per id** by their creator (and by nobody else), but they cannot be *listed* once the job is deleted, because listing is keyed on `job_id` and a missing job returns `404`. Long-term resolution is either a cascade (erase-on-delete) or a job archive/soft-delete; the current rule guarantees the erasure path exists but not discoverability.

## 8. Failure Modes & Trade-offs

| Case | Behaviour | Why |
|---|---|---|
| Recruiter B guesses recruiter A's job id | `404` (not `403`) | No existence oracle for cross-owner probing |
| Reviewer tries `POST/PATCH/DELETE /jobs…` | `403` from the route guard before any handler runs | Route guard is authoritative even for ids they can read |
| Reviewer assigned to job A tries job B | `404` | `find_accessible_job` resolves `None` |
| Assignment payload names a recruiter/candidate | `422` | Role validated per id against `users` before write |
| Admin edits another owner's job | `200` + audit `job.updated` with `cross_owner: true` | Parity plus accountability |
| Admin deletes a template still referenced by a job | `409` (`count_for_template_any`, cross-owner) | Owner-scoped count would have missed foreign references |
| Admin creates an invitation on someone else's job | Works; owner can still manage it | Invitation access derives from the job, not `created_by` |
| Job deleted with invitations still open | Owner/admin can still revoke, decide, **erase**, export by id; job-scoped list `404`s | Union rule (§7) |
| API key held by an admin | Owner-scoped only | `_owner()` forces `role="recruiter"` |
| Reviewer on an assigned job exports CSV | Allowed (`require_staff` on `/export`) | Intentional — review requires seeing the pipeline |

### Accepted quirks / future work

- `GET /api/public/jobs` serialises `reviewer_ids` (and `owner_id`, which equals the key owner) via `JobSummary`. Reviewer user ids are internal but not secret; drop them from the projection if that ever matters.
- `find_accessible_job` performs up to two queries per gate (owner lookup, then id lookup); job-scoped endpoints call it at most once per request.
- Reviewers see candidate PII (names, emails, scores, recordings) for assigned jobs — that is the product intent of "read the pipeline", not an oversight.

## 9. Tests

`backend/tests/test_job_access.py`

| Test | Asserts |
|---|---|
| `test_admin_can_manage_another_recruiters_job` | Admin can `GET`/`PATCH`/`DELETE` another owner's job; `owner_id` surfaced; owner later sees `404` |
| `test_a_recruiter_cannot_see_or_touch_another_recruiters_job` | Cross-owner `GET`/`PATCH`/`DELETE` all `404` |
| `test_reviewer_sees_only_assigned_jobs_and_can_decide` | Unassigned → `[]`/`404`; after assignment → list/detail `200`, other job `404`, `PATCH`/`PUT reviewers` `403`, can decide on assigned, `404` on another job's pipeline |
| `test_reviewer_assignment_rejects_non_reviewers` | Assigning a recruiter id → `422` |
| `test_recruiter_can_list_assignable_reviewers` | `/api/staff/reviewers` `200` for staff, `403` for a practice candidate |
| `test_invitation_survives_job_deletion_for_its_creator` | After `DELETE /jobs/{id}` the job is `404`, another recruiter still gets `404` on erase, but the creator can still erase |

`backend/tests/test_roles.py` → `test_reviewer_is_read_only_on_jobs` covers the guard split (`GET` `200`, writes `403`, templates `403`).

## 10. Verification Commands

```bash
# Backend — full suite (requires reachable Mongo; drops only test_ai_interview_coach)
cd backend
.\venv\Scripts\python -m pytest tests/test_job_access.py tests/test_roles.py -q
.\venv\Scripts\python -m pytest --no-header -rN          # 318 passed
.\venv\Scripts\python -m ruff check app tests scripts

# Frontend — guards and reviewer UI must compile clean
cd frontend
npm run typecheck
npm run build
```

## 11. Deviations & Out of Scope

- **No org/team model.** Ownership is per user; there is no shared mailbox or team-visible pool.
- **No job archive/soft delete.** Deletion is hard; invitations survive it (per §7) but become unlistable.
- **Practice data untouched.** Admins gain no read path into `interviews`, `resumes`, or `job_descriptions`.
- **Two export verbs.** Pipeline CSV/PDF (`require_staff`, quota `exports`) is *not* the same as the per-candidate GDPR export (`GET /{id}/data`, `require_recruiter`).
