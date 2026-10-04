# AI Interview Coach

An AI-powered platform where a candidate uploads their resume and a job description, runs a mock interview with adaptive AI follow-up questions, receives a structured evaluation after every answer, and gets a final performance report with a personalized preparation plan.

> **Status: Phase 9 (hardening) complete.** The full stack is live end-to-end: FastAPI backend (auth, resumes, job descriptions, interviews, evaluations, reports, dashboard stats, RAG-assisted question generation), Next.js frontend wired to the real API, and a **128-test** pytest suite. Operational hardening is in place: rate limiting with `Retry-After`/`X-RateLimit-*` headers, CORS lockdown, structured (JSON) logging with `X-Request-ID` correlation, and uniform error envelopes for every failure path.
>
> **Data-layer note:** the backend uses **MongoDB (Motor)** — connection settings live in `backend/.env` (`MONGO_URI`, `MONGO_DB_NAME`). Indexes are created automatically on startup; there are no migration files to run.

## Quickstart

```bash
cp .env.example .env        # add GROQ_API_KEY (or OPENAI_API_KEY) + a real JWT_SECRET
docker compose up --build
```

| Service   | Port | Purpose |
|-----------|------|---------|
| `frontend`| 3000 | Next.js app (production build) |
| `backend` | 8000 | FastAPI API (`/api`, interactive docs at `/api/docs`) |
| `mongo`   | 27017 | MongoDB 7 (healthcheck) |
| `qdrant`  | 6333 | Qdrant vector store for RAG (healthcheck via volume; set `RAG_ENABLED=false` to skip) |

Open `http://localhost:3000`. The frontend calls the API at `http://localhost:8000/api` (baked in at build time via `NEXT_PUBLIC_API_URL`).

---

## Architecture

```
┌──────────────┐     ┌─────────────────────────────────────────────┐
│   Frontend   │────▶│  FastAPI (API layer - routes only)          │
│  Next.js     │     ├─────────────────────────────────────────────┤
└──────────────┘     │  Service layer (business logic, AppErrors)  │
                     │  Repository layer (DB queries, owns Mongo)  │
                     │  AI layer (llm_service, rag_service)        │
                     │  Cross-cutting: auth · rate limit · logging │
                     │                 CORS · error handlers       │
                     ├─────────────────────────────────────────────┤
                     │  MongoDB (Motor async)  ──▶  indexes        │
                     │  Qdrant (RAG vector store)                  │
                     └─────────────────────────────────────────────┘
```

Design rules:

- **API layer** only validates input/output, applies auth/rate-limit dependencies, and delegates to services.
- **Service layer** owns business logic; raises typed `AppError`s — never returns HTTP responses itself.
- **Repository layer** owns every MongoDB query (`by_alias=True`, responses expose `id`, never `_id`).
- **AI layer** is isolated behind `llm_service.generate_structured(prompt, Schema)` (retries on transient failures) and `rag_service` (Qdrant + fastembed). LLM calls never appear in routes.
- Dependency injection via FastAPI `Depends`, Pydantic v2 models for every request/response (`response_model` on every route).

## Features

**Product (all live against the real API):**

- Registration (Argon2), login returning a JWT, `GET`/`PATCH /api/auth/me`
- Resume upload (PDF/DOCX, magic-byte checked, size limited), list, detail, delete
- Job-description create/list/get/delete
- Interview lifecycle: create (JD required, resume optional) → `start` → `current-question` → `POST /api/questions/{id}/answer` with AI evaluation, adaptive follow-up questions and LLM timeouts → `report` (score, strengths, weaknesses, preparation plan)
- Dashboard statistics (totals, recent interviews, completion rate)
- RAG-assisted question generation (knowledge base ingested into Qdrant by `scripts/ingest_knowledge_base.py`)
- Practice wizard, interview workspace, and result pages in the frontend wired to the live backend

**Operational (Phase 9):**

- Per-client-IP rate limiting on 8 sensitive scopes (register, login, resume upload, JD create, answer submit, interview start/question/report) with `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining` on `429`, and `X-RateLimit-Limit` on allowed requests
- CORS lockdown: explicit origin allow-list, methods (`GET, POST, PATCH, DELETE`) and headers (`Authorization, Content-Type`), **credentials disabled** (the SPA uses a Bearer token, never cookies)
- Structured logging: JSON in production (`LOG_FORMAT=auto|text|json`), request-scoped `X-Request-ID` correlation header, per-request log line (method/path/status/duration/client IP), never logs authorization material
- Uniform error envelopes (`{"detail": ..., "code": ...}`) for `400/401/403/404/405/409/413/422/429/500/503`; unhandled exceptions return a generic `500 internal_error` with the stack trace only in server logs
- Oversized-body rejection (413) before the body is read; health check degrades to `503` when Mongo is unreachable

## Tech Stack

| Layer     | Technology |
|-----------|------------|
| Backend   | Python 3.12+, FastAPI, Pydantic v2, Uvicorn |
| Database  | MongoDB (Motor async) |
| Auth      | JWT (PyJWT), Argon2 password hashing |
| AI        | OpenAI-compatible client (`openai` or `groq` provider), 90s timeout, retries, structured-output generation |
| RAG       | Qdrant + fastembed (`BAAI/bge-small-en-v1.5`) |
| Frontend  | Next.js 16, TypeScript, Tailwind CSS v4, Lucide React, React 19 |
| Infra     | Docker, Docker Compose |

## Folder Structure

```
ai-interview-coach/
├── backend/
│   ├── app/
│   │   ├── main.py                 # app, lifespan, middleware, error handlers, CORS, request logging
│   │   ├── api/                    # API layer (routes + dependency wiring)
│   │   │   ├── auth.py  resumes.py  job_descriptions.py
│   │   │   ├── interviews.py       # create/list/start/current-question/report
│   │   │   ├── questions.py        # POST /{question_id}/answer
│   │   │   ├── dashboard.py        # GET /stats
│   │   │   └── deps.py
│   │   ├── core/                   # config, security, database, logging, exceptions, rate_limit
│   │   ├── models/  schemas/       # domain models, request/response schemas
│   │   ├── services/               # auth, resume, JD, interview, dashboard, llm, rag,
│   │   │                           # embedding, knowledge_loader, parsers/
│   │   ├── repositories/           # user, resume, JD, interview queries
│   │   ├── prompts/                # LLM prompt templates
│   ├── scripts/ingest_knowledge_base.py
│   ├── tests/                      # 128 tests (see "Testing")
│   ├── .env.example  requirements*.txt  ruff.toml  Dockerfile
├── frontend/                       # Next.js app (Dockerfile, .env.example, see "Running Frontend")
├── data/knowledge_base/            # RAG sources ingested into Qdrant
├── docker-compose.yml              # frontend + backend + mongo + qdrant
├── .env.example                    # root template (compose interpolation + backend/.env)
└── README.md
```

## Environment Variables

Copy `.env.example` to `.env` (repo root, read by docker compose) **and** to `backend/.env` (read by the FastAPI app). The frontend reads `frontend/.env.local` (from `frontend/.env.example`).

| Variable | Description | Default |
|---|---|---|
| `APP_NAME` | Application name | `AI Interview Coach` |
| `ENVIRONMENT` | `development` / `test` / `production` | `development` |
| `DEBUG` | Debug flag | `false` |
| `API_PREFIX` | API mount path | `/api` |
| `LOG_LEVEL` | Python log level | `INFO` |
| `LOG_FORMAT` | Log shape: `auto` (JSON in production, text elsewhere), `text`, `json` | `auto` |
| `CORS_ORIGINS` | Allowed origins (comma-separated or JSON array; `*` rejected in production) | `http://localhost:3000,...` |
| `MONGO_URI` / `MONGO_DB_NAME` | MongoDB connection / database | `mongodb://localhost:27017` / `ai_interview_coach` |
| `STORAGE_DIR` | Resume storage directory (gitignored) | `data/resumes` |
| `MAX_UPLOAD_BYTES` | Upload size limit (413 above) | `5242880` |
| `MAX_BODY_BYTES` | Refuse whole request bodies above this size (413) | `10485760` |
| `JWT_SECRET` | Signing secret (**required in production**) | dev-only value |
| `JWT_ALGORITHM` / `JWT_EXPIRES_MINUTES` | Token algorithm / lifetime | `HS256` / `1440` |
| `RATE_LIMIT_ATTEMPTS` / `RATE_LIMIT_WINDOW_SECONDS` | Sliding-window budget per client IP and scope | `20` / `60` |
| `TRUST_PROXY_HEADERS` | Trust `X-Forwarded-For` for rate limiting (only behind your own proxy) | `false` |
| `LLM_PROVIDER` | `openai` or `groq` | `groq` |
| `GROQ_API_KEY` / `OPENAI_API_KEY` | Provider credentials (never exposed to the frontend) | — |
| `GROQ_MODEL` / `OPENAI_MODEL` | Model names | `openai/gpt-oss-20b` / `gpt-4o` |
| `RAG_ENABLED` | Turn RAG-assisted question generation on/off | `true` |
| `QDRANT_URL` / `QDRANT_API_KEY` | Qdrant server URL (`http(s)://…`), embedded path, or `:memory:` | `http://localhost:6333` |
| `RAG_TOP_K` | Knowledge chunks injected per question (3–5) | `5` |
| `NEXT_PUBLIC_API_URL` | Backend base URL — **baked into the frontend at build time** | `http://localhost:8000/api` |

> Production boot fails fast if `JWT_SECRET` still holds the default value and if `CORS_ORIGINS` contains `*`.

## Installation (without Docker)

### Prerequisites

- Python 3.12+, MongoDB (local, Docker, or Atlas)
- Node.js 20+ (frontend)
- A Groq or OpenAI API key for LLM features (everything else runs without one; LLM-backed calls return `503` when the provider is unreachable)

### Backend

```bash
cd backend
python -m venv venv
# Linux/macOS: source venv/bin/activate   Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
cp ../.env.example .env      # point MONGO_URI at a MongoDB you can reach, add your LLM key
uvicorn app.main:app --reload
```

- API base: `http://localhost:8000/api` · Health: `GET /api/health` · Docs: `http://localhost:8000/api/docs` (disabled when `ENVIRONMENT=production`)

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000/api
npm run dev                   # http://localhost:3000
# production: npm run build && npm run start
```

## Running the Full Stack with Docker

```bash
cp .env.example .env         # set GROQ_API_KEY (or OPENAI_API_KEY) and JWT_SECRET
docker compose up --build
```

- `backend` mounts `./backend` (so a `--reload`-style dev loop still works by swapping the command) and seeds env from `docker-compose.yml` + `backend/.env`.
- `frontend` is built with `NEXT_PUBLIC_API_URL` as a build arg (defaults to `http://localhost:8000/api`) and starts only after the backend healthcheck passes.
- `qdrant` data lives in the `qdrant_data` volume; run `docker compose run --rm backend python -m scripts.ingest_knowledge_base` to (re)ingest the knowledge base.
- There is **no Redis service — by design** (see "Operational decisions").

## API Documentation

Interactive OpenAPI docs are at **`/api/docs`** while the server runs.

### Endpoints

| Method | Path | Auth | Description | Success |
|---|---|---|---|---|
| `POST` | `/api/auth/register` | — | Create account (rate limited) | `201` |
| `POST` | `/api/auth/login` | — | Get JWT (rate limited) | `200` |
| `GET`/`PATCH` | `/api/auth/me` | Bearer | Current user / update profile | `200` |
| `POST` | `/api/resumes/upload` | Bearer | Upload PDF/DOCX resume (rate limited) | `201` |
| `GET` | `/api/resumes` | Bearer | List resumes (without raw text) | `200` |
| `GET` | `/api/resumes/{id}` | Bearer | Resume detail | `200` |
| `DELETE` | `/api/resumes/{id}` | Bearer | Delete resume + file | `204` |
| `POST` | `/api/job-descriptions` | Bearer | Save a job description (rate limited) | `201` |
| `GET` | `/api/job-descriptions` | Bearer | List summaries | `200` |
| `GET` | `/api/job-descriptions/{id}` | Bearer | Job description detail | `200` |
| `DELETE` | `/api/job-descriptions/{id}` | Bearer | Delete job description | `204` |
| `POST` | `/api/interviews` | Bearer | Create interview (`jd_id` required, `resume_id` optional) | `201` |
| `GET` | `/api/interviews` | Bearer | List your interviews (summaries) | `200` |
| `GET` | `/api/interviews/{id}` | Bearer | Interview detail | `200` |
| `POST` | `/api/interviews/{id}/start` | Bearer | Generate the first question (rate limited) | `200` |
| `GET` | `/api/interviews/{id}/current-question` | Bearer | Resume at the current question (rate limited) | `200` |
| `POST` | `/api/questions/{question_id}/answer` | Bearer | Submit an answer → evaluation + next question (rate limited) | `200` |
| `GET` | `/api/interviews/{id}/report` | Bearer | Final report + preparation plan (rate limited) | `200` |
| `GET` | `/api/dashboard/stats` | Bearer | Dashboard statistics | `200` |
| `GET` | `/api/health` | — | Health check (DB ping → `503` if down) | `200` |

Errors: `401` missing/invalid/expired token · `404` unknown id · `409` duplicate email / already completed · `413` oversized body · `422` validation · `429` rate limited · `503` LLM/database unavailable.

#### Error envelope

```json
{ "detail": "Human readable message", "code": "conflict" }
```

- `422` responses carry a **list** in `detail` (one entry per field, each with `msg`).
- `429` additionally carries `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining: 0`.
- Every response includes `X-Request-ID`; the same value is attached to that request's log line.

#### Rate-limited scopes

`register` · `login` · `resume_upload` · `job_description_create` · `answer_submission` · `interview_start` · `interview_question` · `interview_report` — each with an independent budget (`RATE_LIMIT_ATTEMPTS` per `RATE_LIMIT_WINDOW_SECONDS`, keyed by client IP).

## Operational decisions

- **Rate limiting is in-process — no Redis.** The deployment target is a single Uvicorn process; there are no background jobs and no other shared state (long LLM calls stay on the request path with 90s timeouts). An in-memory sliding window in `app/core/rate_limit.py` is honest about that: no extra service, no serialization layer, and a `429` that is always accurate for the process serving the request. If you scale horizontally, the limiter is one self-contained module — swap its storage for Redis before running multiple replicas.
- **CORS allows only `GET/POST/PATCH/DELETE` + `Authorization/Content-Type`, credentials off.** The SPA authenticates with a `Bearer` header from `localStorage`, never cookies, so `Access-Control-Allow-Credentials` would add CSRF surface without benefit.
- **Structured logs carry a `X-Request-ID`.** `LOG_FORMAT=auto` emits JSON in production (one line per request: method, path, status, duration, client IP, request id) and human-readable text elsewhere; error envelopes never contain stack traces, and authorization headers are never logged.

## Testing

```bash
cd backend
# Windows
.\venv\Scripts\python -m pytest -q
# Linux / macOS
.venv/bin/python -m pytest -q
```

- Requires a reachable MongoDB: `MONGO_URI` comes from `backend/.env`. Tests run against a dedicated database (`test_ai_interview_coach`) dropped before and after the run — your data in `ai_interview_coach` is untouched.
- `ENVIRONMENT=test` disables rate limiting for the suite (the dedicated `test_rate_limit.py` flips it back on where it is under test) and forces an in-memory Qdrant.
- LLM calls are mocked; no real LLM API calls are made during test runs.
- Lint/format: `ruff check app tests scripts` and `ruff format --check app tests scripts` (config in `backend/ruff.toml`).

**Current suite: 128 tests** — auth (register/login/me, throttling, envelopes), config/settings validation, resumes, job descriptions, interview lifecycle + answers + report, dashboard, RAG, `LLMService` retry policy, **CORS preflight/lockdown**, **rate limiting (headers, scope isolation, window expiry, test no-op, proxy keying)**, **error handlers (405/400/500/413/422, health degraded)**, and **logging (JSON formatter, format resolution, request-id middleware, no auth material logged)**.

## Frontend Checks

```bash
cd frontend
npm run typecheck     # tsc --noEmit (noUnusedLocals/Parameters enabled)
npm run build
```

No ESLint/Prettier is configured yet.

## Security Notes

- Passwords hashed with Argon2 (never stored or logged in plaintext)
- JWT signed with `JWT_SECRET`; production startup fails on the default secret and on `CORS_ORIGINS=*`
- Protected routes validated per request; Pydantic input validation on every endpoint
- Per-IP, per-scope in-process rate limiting; `429` carries `Retry-After` and `X-RateLimit-*`; `TRUST_PROXY_HEADERS` stays off unless a proxy you control sets `X-Forwarded-For`
- Uploads validated for extension, magic bytes, and size; stored outside the web root and never served publicly
- CORS restricted to configured origins with an explicit method/header allow-list and no credentials; security headers set in `next.config.ts` (`X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`)
- Auth failures are real `401`s; an expired token clears storage and redirects to `/login`
- Untrusted document text is wrapped in tags and capped before it reaches the model (prompt-injection and cost control)
- Bodies above `MAX_BODY_BYTES` are refused before being read; `/api/docs` is disabled when `ENVIRONMENT=production`
- Unhandled exceptions return `500 {"detail": "Internal server error", "code": "internal_error"}` — stack traces stay in server logs; request logs never include `Authorization` headers
- `.env` files are gitignored; only `.env.example` is committed — real keys never belong in the repository
