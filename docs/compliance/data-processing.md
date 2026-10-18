# Data-processing record (technical annex)

This document is the human-readable companion to the machine-readable record at
`GET /api/compliance` (admin-only). It describes what personal data the platform
processes, how it is protected, and how data-subject rights are honoured. It is
material for a Data Processing Agreement (DPA), not legal advice.

## Roles

- **Controller:** the deploying company (the recruiter).
- **Processor:** this platform, on the controller's infrastructure.
- **Candidate:** a guest — no account is created; access is via a magic link.

## Personal data processed

| Category | Where | Notes |
| --- | --- | --- |
| Candidate identity | `screening_invitations` | name, email (used to send the link) |
| Interview content | `interviews` | questions, answers, AI evaluations, report |
| Proctoring data | `interviews.proctoring_session` | events, integrity signals (advisory only) |
| Session recording | GridFS bucket `interview_recordings` | chunked video, proctored rounds only |
| Staff identity | `users` | name, email, role, Argon2 password hash |
| Metering | `llm_usage` | token counts, cost, acting user id (no content) |

The AI never makes a hiring decision: scores are advisory and a human records
the decision.

## Retention and erasure

- Session data older than `DATA_RETENTION_DAYS` (default 365) is destroyed by the
  `retention.purge` job / `POST /api/invitations/retention/purge` (admin).
- Invitation rows are **anonymized, not deleted** (`[erased]`,
  `erased+<id>@erased.invalid`), so aggregate analytics survive.
- Erasure removes the interview, the GridFS recording chunks, the candidate's
  synthesized job description, and invalidates the magic link.

## Data-subject rights

- **Access:** `GET /api/invitations/{id}/data` returns everything held about a
  candidate as JSON (recruiter-gated; excludes the token hash and guest id).
- **Erasure:** `POST /api/invitations/{id}/erase` (recruiter-gated) or the
  retention purge.
- **Rectification:** candidate identity fields are corrected by the recruiter in
  the review workspace.

## Security controls

- **Encryption in transit:** TLS terminated at the deployment's ingress.
- **Encryption at rest:** app-managed secrets (ATS webhook signing secret) are
  encrypted with AES-128-CBC + HMAC via Fernet, keyed by `FIELD_ENCRYPTION_KEY`.
  One-way values (password and token hashes) are already non-reversible. Disk /
  storage-engine encryption is the operator's responsibility.
- **Access control:** role-based (`admin`, `recruiter`, `reviewer`) with audit
  logging of privileged actions; the public API uses scoped, revocable keys.
- **Rate limiting & quotas:** per-IP rate limits plus per-role daily quotas
  (`ROLE_LIMITS`) and optional seat (`MAX_STAFF_SEATS`) and spend
  (`MONTHLY_LLM_BUDGET_USD`) caps.

## Subprocessors

The only outbound processing is the configured AI provider (LLM inference, and
speech-to-text when `TRANSCRIPTION_PROVIDER` is set) and, if configured, the
transactional email provider. Both are listed at `GET /api/compliance`.

## Residency

`DEPLOYMENT_REGION` documents where the platform and its database run. Data is
not copied across regions by the platform itself; the AI provider's own region
handling applies to inference requests.

## Time zone handling

Instants are stored and compared in **UTC** (MongoDB stores UTC; naive values
returned by the driver are treated as UTC). Everything a person reads is
rendered in **Asia/Kolkata (IST, +05:30, no DST)** — email and PDF copy,
structured log lines, API JSON responses (`backend/app/core/timeutil.py`), and
the frontend (`frontend/lib/datetime.ts`). This is a display convention only: it
does not change what is stored, how long it is retained, or any retention/erasure
deadline.

## Not yet shipped

- **SSO/SAML:** authentication is email + password today. Federated sign-in
  requires an external identity provider (Okta, Entra ID, Google Workspace, …)
  and is intentionally out of scope until one is chosen; no partial SAML stub
  ships, to avoid a false sense of coverage.
- **Paid billing:** seats and spend are capped by configuration
  (`MAX_STAFF_SEATS`, `MONTHLY_LLM_BUDGET_USD`); integration with a payment
  provider (e.g. Stripe) is pending a vendor decision.
