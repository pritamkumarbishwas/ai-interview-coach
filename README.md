# AI Interview Coach

An AI-powered platform where a candidate uploads their resume and a job description, runs a mock interview, receives AI evaluation with adaptive follow-up questions, and gets a detailed performance report with a personalized preparation plan.

> **Status: Phase 1 backend + redesigned frontend complete.** The backend delivers auth (JWT), resume upload/parsing, job-description management, health/rate limiting, and a pytest suite. The frontend is a full Next.js + TypeScript + Tailwind CSS product UI with a warm-orange design system. Login/register, profile, `/resumes`, and `/job-descriptions` are wired to the live backend; the interview flow (workspace, results, report) is still driven by **mock data** (`frontend/data/mock.ts`) until interview endpoints land.
>
> **Data-layer note:** the backend uses **MongoDB (Motor)** — connection settings live in `backend/.env` (`MONGO_URI`, `MONGO_DB_NAME`). Indexes are created automatically on startup; the leftover `migrations/` and `alembic.ini` under `backend/` are legacy and unused.

---

## Architecture

```
┌──────────────┐     ┌─────────────────────────────────────────────┐
│   Frontend   │────▶│  FastAPI (API layer - routes only)         │
│  Next.js     │     ├─────────────────────────────────────────────┤
└──────────────┘     │  Service layer (business logic)             │
                     │  Repository layer (DB queries)              │
                     │  AI layer (LLM / RAG - later phases)        │
                     ├─────────────────────────────────────────────┤
                     │  MongoDB (Motor async)  ──▶  indexes         │
                     │  created automatically on startup           │
                     └─────────────────────────────────────────────┘
```

Design rules:

- **API layer** only validates input/output and delegates to services.
- **Service layer** owns business logic and transactions.
- **Repository layer** owns database queries.
- **AI layer** (later phases) is isolated behind an `LLMService` abstraction — LLM calls never appear in routes.
- Dependency injection via FastAPI `Depends`, Pydantic v2 models for every request/response.

## Features

- User registration with password hashing (Argon2)
- Login returning a JWT access token; `PATCH /api/auth/me` updates your profile
- Protected `GET /api/auth/me` via `Authorization: Bearer` header
- Resume upload (PDF/DOCX, magic-byte checked, size limited), listing, download and delete
- Job-description create/list/get/delete with a stored summary snippet
- In-memory rate limiting on `/register` and `/login`
- Structured JSON error responses with proper HTTP status codes (401/404/409/413/422/500)
- Request validation with Pydantic v2
- Configurable settings from environment variables
- Health check that reports database degradation as `503`
- Pytest suite (no real LLM/network calls)
- Docker Compose infrastructure: backend + MongoDB

### Planned (later phases)

Interview creation · AI question generation · Answer evaluation · Adaptive follow-ups · Final report & preparation plan · RAG · Next.js dashboard stats

## Tech Stack

| Layer     | Technology |
|-----------|------------|
| Backend   | Python 3.12+, FastAPI, Pydantic v2, Uvicorn |
| Database  | MongoDB (Motor async) |
| Auth      | JWT (PyJWT), Argon2 password hashing |
| AI        | OpenAI-compatible client (`openai` or `groq` provider), 90s timeout, retries |
| Frontend  | Next.js 16, TypeScript, Tailwind CSS v4, Lucide React, React 19 |
| Infra     | Docker, Docker Compose |

## Folder Structure

```
ai-interview-coach/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, lifespan, middleware, error handlers
│   │   ├── api/                    # API layer (routes + dependency wiring)
│   │   │   ├── auth.py
│   │   │   ├── resumes.py
│   │   │   ├── job_descriptions.py
│   │   │   └── deps.py
│   │   ├── core/                   # config, security, database, logging, exceptions, rate_limit
│   │   ├── models/                 # Pydantic domain models
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── services/               # business logic (auth, LLM, resume, JD)
│   │   ├── repositories/           # DB queries
│   │   ├── prompts/                # prompt templates (later phases)
│   │   └── utils/                  # document parsers (pdf/docx/text)
│   ├── migrations/                 # legacy Alembic files (unused)
│   ├── data/resumes/               # uploaded files (private, gitignored)
│   ├── tests/                      # pytest suite
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── ruff.toml
│   ├── Dockerfile
│   └── alembic.ini                 # legacy (unused)
├── frontend/                       # Next.js app (see "Running Frontend")
├── data/knowledge_base/            # RAG knowledge sources (later phases)
├── docker-compose.yml
├── .env.example
└── README.md
```

## Environment Variables

Copy `.env.example` to `.env` (repo root, used by docker compose) and to `backend/.env` (read by the FastAPI app).

| Variable | Description | Default |
|---|---|---|
| `APP_NAME` | Application name | `AI Interview Coach` |
| `ENVIRONMENT` | `development` / `test` / `production` | `development` |
| `DEBUG` | Debug flag | `false` |
| `API_PREFIX` | API mount path | `/api` |
| `LOG_LEVEL` | Python log level | `INFO` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:3000,...` |
| `MONGO_URI` | MongoDB connection string | `mongodb://localhost:27017` |
| `MONGO_DB_NAME` | Database name | `ai_interview_coach` |
| `STORAGE_DIR` | Resume storage directory | `data/resumes` |
| `MAX_UPLOAD_BYTES` | Upload size limit (413 above) | `5242880` |
| `JWT_SECRET` | Signing secret (**required in production**) | dev-only value |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `JWT_EXPIRES_MINUTES` | Token lifetime | `1440` |
| `RATE_LIMIT_ATTEMPTS` / `RATE_LIMIT_WINDOW_SECONDS` | Login/register throttle | `20` / `60` |
| `LLM_PROVIDER` | `openai` or `groq` | `groq` |
| `GROQ_API_KEY` / `OPENAI_API_KEY` | Provider credentials | — |
| `GROQ_MODEL` / `OPENAI_MODEL` | Model names | `openai/gpt-oss-20b` / `gpt-4o` |

> API keys are never hard-coded and never exposed to the frontend.

## Installation

### Prerequisites

- Python 3.12+
- MongoDB (local, Docker, or Atlas) — used by the app and the test suite
- Docker + Docker Compose (optional, for infrastructure)
- Node.js 20+ (frontend)

### Local setup (without Docker)

```bash
cd backend
python -m venv .venv

# Linux / macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements-dev.txt

# configure environment
cp ../.env.example ../.env    # then point MONGO_URI at a MongoDB you can reach
```

## Docker Setup

```bash
cp .env.example .env      # edit values, especially JWT_SECRET
docker compose up --build
```

This starts:

| Service   | Port | Purpose |
|-----------|------|---------|
| `backend` | 8000 | FastAPI app (creates indexes on start, `GET /api/health` ping) |
| `mongo`   | 27017 | MongoDB 7 with a healthcheck |

Inside Compose the database host is `mongo` — `MONGO_URI` is set to `mongodb://mongo:27017` in `docker-compose.yml`.

> The previously defined `postgres`, `qdrant`, and `redis` services were unused by the code and have been removed (commented examples remain in `docker-compose.yml`).

## Database Indexes

There are no migration files to run: the application creates the indexes it needs on startup (`email` unique on `users`, lookups on `resumes` / `job_descriptions`). Changing a model usually needs nothing beyond a restart.

```bash
# inspect what exists
docker compose exec mongo mongosh --quiet --eval "db.getCollectionNames()"
```

## Running Backend

```bash
cd backend

# with a reachable MongoDB (see MONGO_URI in .env)
uvicorn app.main:app --reload
```

- API base: `http://localhost:8000/api`
- Health check: `GET /api/health`
- Interactive docs: `http://localhost:8000/api/docs`

## Running Frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000/api

npm run dev                  # development → http://localhost:3000
# or
npm run build && npm run start   # production build
```

Pages:

| Route | Purpose | Data |
|---|---|---|
| `/login`, `/register` | Auth (wired to live backend) | Live API |
| `/dashboard` | Stats, recent interviews, onboarding, weekly goal | Mock |
| `/interviews` | Interview list with search + type filters | Mock |
| `/practice` | 3-step setup: resume → job description → session config | Mock |
| `/interviews/[id]` | Interview workspace: video, AI interviewer, live score, conversation, feedback, evaluation | Mock (interactive) |
| `/interviews/[id]/result` | Score, performance breakdown, strengths, AI recommendations | Mock |
| `/results` | Completed-interview reports with sorting | Mock |
| `/profile` | Account (live), skills/preferences/progress (mock) | Mixed |
| `/resumes` | Manage uploaded resumes: upload, list, delete | Live API |
| `/job-descriptions` | Create, list, delete saved job descriptions | Live API |

Design system: orange accent (`#F7931E`) reserved for CTAs, active navigation, scores, AI status, and progress; tokens live in `frontend/app/globals.css`, product data in `frontend/data/mock.ts`.

Auth token is stored in `localStorage` (`aic_access_token`) and attached by the axios interceptor in `frontend/lib/api.ts`. CORS must include `http://localhost:3000`.

## API Documentation

Interactive OpenAPI docs are available at **`/api/docs`** once the server is running.

### Endpoints

| Method | Path | Auth | Description | Success |
|---|---|---|---|---|
| `POST` | `/api/auth/register` | — | Create account (rate limited) | `201` |
| `POST` | `/api/auth/login` | — | Get JWT (rate limited) | `200` |
| `GET` | `/api/auth/me` | Bearer | Current user | `200` |
| `PATCH` | `/api/auth/me` | Bearer | Update profile (`{"name": "..."}`) | `200` |
| `POST` | `/api/resumes/upload` | Bearer | Upload PDF/DOCX resume | `201` |
| `GET` | `/api/resumes` | Bearer | List resumes (without raw text) | `200` |
| `GET` | `/api/resumes/{id}` | Bearer | Resume detail | `200` |
| `DELETE` | `/api/resumes/{id}` | Bearer | Delete resume + file | `204` |
| `POST` | `/api/job-descriptions` | Bearer | Save a job description | `201` |
| `GET` | `/api/job-descriptions` | Bearer | List summaries | `200` |
| `GET` | `/api/job-descriptions/{id}` | Bearer | Job description detail | `200` |
| `DELETE` | `/api/job-descriptions/{id}` | Bearer | Delete job description | `204` |
| `GET` | `/api/health` | — | Health check (DB ping → `503` if down) | `200` |

#### `POST /api/auth/register`

```json
{ "name": "Jane Doe", "email": "jane@example.com", "password": "secret12345" }
```

→ `201`

```json
{ "id": "650f...", "name": "Jane Doe", "email": "jane@example.com", "created_at": "2026-10-03T11:57:17" }
```

Errors: `409` duplicate email · `422` validation · `429` rate limited

#### `POST /api/auth/login`

```json
{ "email": "jane@example.com", "password": "secret12345" }
```

→ `200`

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": { "id": "650f...", "name": "Jane Doe", "email": "jane@example.com", "created_at": "..." }
}
```

Errors: `401` invalid credentials · `429` rate limited

#### `GET /api/auth/me`

```
Authorization: Bearer <access_token>
```

→ `200` user object · `401` missing/invalid/expired token

#### Error envelope

```json
{ "detail": "Human readable message", "code": "conflict" }
```

## Testing

```bash
cd backend
# Windows
.\.venv\Scripts\python -m pytest -v
# Linux / macOS
.venv/bin/python -m pytest -v
```

- Requires a reachable MongoDB: `MONGO_URI` comes from `backend/.env`.
- Tests run against a dedicated database (`test_ai_interview_coach`) that is dropped before and after the run — your data in `ai_interview_coach` is untouched.
- `ENVIRONMENT=test` disables rate limiting for the suite.
- LLM calls are mocked; no real LLM API calls are made during test runs.
- Lint: `ruff check .` and `ruff format --check .` (config in `backend/ruff.toml`).

Current suite: **32 tests** — registration (success/validation/duplicate/case-normalisation), login (success/failure/throttled), `GET`/`PATCH /me`, resume upload validation/list/404s, job-description create/list/get/delete (LLM mocked) plus save-while-LLM-is-down, health check, and `LLMService` configuration/retry behaviour.

## Frontend Checks

```bash
cd frontend
npm run typecheck     # tsc --noEmit (noUnusedLocals/Parameters enabled)
npm run build
```

No ESLint/Prettier is configured yet.

## Security Notes

- Passwords hashed with Argon2 (never stored or logged in plaintext)
- JWT signed with `JWT_SECRET`; production startup fails if the default secret is used
- Protected routes validated per request
- Pydantic input validation on every endpoint
- Login/register throttled in-process (`RATE_LIMIT_*`)
- Uploads validated for extension, magic bytes, and size; stored outside the web root and never served publicly
- CORS restricted to configured origins; security headers set in `next.config.ts`
- Auth failures are surfaced as real 401s; an expired token clears storage and redirects to `/login`
