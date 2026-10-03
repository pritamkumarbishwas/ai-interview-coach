# AI Interview Coach

An AI-powered platform where a candidate uploads their resume and a job description, runs a mock interview, receives AI evaluation with adaptive follow-up questions, and gets a detailed performance report with a personalized preparation plan.

> **Status: Phase 1 backend + redesigned frontend complete.** The backend delivers the FastAPI skeleton, auth (JWT), and tests. The frontend is a full Next.js + TypeScript + Tailwind CSS product UI with a warm-orange design system: dashboard, my interviews, practice wizard, interactive interview workspace, results, report, and profile are all driven by **mock data** (`frontend/data/mock.ts`) so the product is fully explorable without backend phases. Login/register remain wired to the live backend, and the auth guards/services are kept for later phases.
>
> **Data-layer note:** the backend was migrated from PostgreSQL/SQLAlchemy to **MongoDB (Motor)** — connection settings live in `backend/.env` (`MONGO_URI`, `MONGO_DB_NAME`). The `migrations/`, `alembic.ini`, and Postgres entries in `docker-compose.yml` are legacy and unused while MongoDB is active.

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
                     │  SQLAlchemy async  ──▶  PostgreSQL          │
                     │  Alembic migrations                         │
                     └─────────────────────────────────────────────┘
```

Design rules:

- **API layer** only validates input/output and delegates to services.
- **Service layer** owns business logic and transactions.
- **Repository layer** owns database queries.
- **AI layer** (later phases) is isolated behind an `LLMService` abstraction — LLM calls never appear in routes.
- Dependency injection via FastAPI `Depends`, Pydantic v2 models for every request/response.

## Features (Phase 1)

- User registration with password hashing (Argon2)
- Login returning a JWT access token
- Protected `GET /api/auth/me` via `Authorization: Bearer` header
- Structured JSON error responses with proper HTTP status codes (401/409/422/500)
- Request validation with Pydantic v2
- Configurable settings from environment variables
- Alembic migrations
- Pytest suite (no real LLM/network calls)
- Docker Compose infrastructure: backend, PostgreSQL, Qdrant, Redis

### Planned (later phases)

Resume upload & parsing · Job description analysis · Interview creation · AI question generation · Answer evaluation · Adaptive follow-ups · Final report & preparation plan · RAG on Qdrant · Next.js dashboard

## Tech Stack

| Layer     | Technology |
|-----------|------------|
| Backend   | Python 3.12+, FastAPI, Pydantic v2, Uvicorn |
| Database  | PostgreSQL, SQLAlchemy 2 (async), Alembic |
| Auth      | JWT (PyJWT), Argon2 password hashing |
| AI / RAG  | OpenAI-compatible client, Qdrant, Sentence Transformers (later phases) |
| Frontend  | Next.js 16, TypeScript, Tailwind CSS v4, Lucide React, React 19 |
| Infra     | Docker, Docker Compose |

## Folder Structure

```
ai-interview-coach/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, middleware, error handlers
│   │   ├── api/                    # API layer (routes + dependency wiring)
│   │   │   ├── auth.py
│   │   │   └── deps.py
│   │   ├── core/                   # config, security, database, logging, exceptions
│   │   ├── models/                 # SQLAlchemy ORM models
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── services/               # business logic
│   │   ├── repositories/           # DB queries
│   │   ├── prompts/                # prompt templates (later phases)
│   │   └── utils/                  # document parsers (later phases)
│   ├── migrations/                 # Alembic migrations
│   │   └── versions/
│   ├── tests/                      # pytest suite
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── Dockerfile
│   └── alembic.ini
├── frontend/                       # Next.js app (see "Running Frontend")
├── data/knowledge_base/            # RAG knowledge sources (later phases)
├── docker-compose.yml
├── .env.example
└── README.md
```

## Environment Variables

Copy `.env.example` to `.env` and adjust it.

| Variable | Description | Default |
|---|---|---|
| `APP_NAME` | Application name | `AI Interview Coach` |
| `ENVIRONMENT` | `development` / `test` / `production` | `development` |
| `DEBUG` | Debug flag | `false` |
| `API_PREFIX` | API mount path | `/api` |
| `LOG_LEVEL` | Python log level | `INFO` |
| `DATABASE_URL` | Async SQLAlchemy URL | `postgresql+asyncpg://...@localhost:5432/ai_interview_coach` |
| `DATABASE_ECHO` | Echo SQL statements | `false` |
| `JWT_SECRET` | Signing secret (**required in production**) | dev-only value |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `JWT_EXPIRES_MINUTES` | Token lifetime | `1440` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:3000` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Compose DB bootstrap | `ai_interview` |
| `POSTGRES_PORT` / `QDRANT_PORT` / `REDIS_PORT` | Infra ports | `5432` / `6333` / `6379` |

> API keys are never hard-coded and never exposed to the frontend.

## Installation

### Prerequisites

- Python 3.12+
- Docker + Docker Compose (for infrastructure)
- Node.js 20+ (frontend, later phases)

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
cp ../.env.example ../.env    # then edit DATABASE_URL to use localhost
```

## Docker Setup

```bash
cp .env.example .env      # edit values, especially JWT_SECRET
docker compose up --build
```

This starts:

| Service    | Port | Purpose |
|------------|------|---------|
| `backend`  | 8000 | FastAPI app (runs `alembic upgrade head` on start) |
| `postgres` | 5432 | Database |
| `qdrant`   | 6333 | Vector store (used in RAG phase) |
| `redis`    | 6379 | Cache / queues (if required) |

Inside Compose the database host is `postgres` — `docker compose` overrides `DATABASE_URL` automatically.

## Database Migration

```bash
cd backend

# create a new revision after model changes
alembic revision --autogenerate -m "describe change"

# apply migrations
alembic upgrade head

# inspect
alembic current
alembic history
```

With Docker, migrations run automatically when the backend container starts:

```bash
docker compose exec backend alembic upgrade head
```

## Running Backend

```bash
cd backend

# with a local PostgreSQL (see DATABASE_URL in .env)
alembic upgrade head
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
| `/profile` | Account, skills, preferences, progress | Mock |
| `/resumes`, `/job-descriptions` | Manage uploaded resumes and saved JDs | Mock |

Design system: orange accent (`#F7931E`) reserved for CTAs, active navigation, scores, AI status, and progress; tokens live in `frontend/app/globals.css`, product data in `frontend/data/mock.ts`.

Auth token is stored in `localStorage` (`aic_access_token`) and attached by the axios interceptor in `frontend/lib/api.ts`. CORS must include `http://localhost:3000`.

## API Documentation

Interactive OpenAPI docs are available at **`/api/docs`** once the server is running.

### Phase 1 endpoints

| Method | Path | Auth | Description | Success |
|---|---|---|---|---|
| `POST` | `/api/auth/register` | — | Create account | `201` |
| `POST` | `/api/auth/login` | — | Get JWT | `200` |
| `GET` | `/api/auth/me` | Bearer | Current user | `200` |
| `GET` | `/api/health` | — | Health check | `200` |

#### `POST /api/auth/register`

```json
{ "name": "Jane Doe", "email": "jane@example.com", "password": "secret12345" }
```

→ `201`

```json
{ "id": 1, "name": "Jane Doe", "email": "jane@example.com", "created_at": "2026-10-03T11:57:17" }
```

Errors: `409` duplicate email · `422` validation

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
  "user": { "id": 1, "name": "Jane Doe", "email": "jane@example.com", "created_at": "..." }
}
```

Errors: `401` invalid credentials

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
pytest -v
```

- Uses an in-memory SQLite database — no PostgreSQL or Docker required.
- LLM calls are mocked/absent in Phase 1 tests; later phases will mock all AI calls.
- No real LLM API calls are ever made during normal test runs.

Current suite (13 tests): registration success/validation/duplicate, login success/failure, `GET /me` with valid/missing/invalid tokens, deleted-user token rejection, health check.

## Security Notes

- Passwords hashed with Argon2 (never stored or logged in plaintext)
- JWT signed with `JWT_SECRET`; production startup fails if the default secret is used
- Protected routes validated per request
- Pydantic input validation on every endpoint
- CORS restricted to configured origins
- Resume files will be stored privately (never publicly accessible) in a later phase
