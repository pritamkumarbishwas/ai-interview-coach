import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.agui import router as agui_router
from app.api.api_keys import router as api_keys_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.compliance import router as compliance_router
from app.api.dashboard import router as dashboard_router
from app.api.interviews import router as interviews_router
from app.api.job_descriptions import router as job_descriptions_router
from app.api.jobs import router as jobs_router
from app.api.public import router as public_router
from app.api.questions import router as questions_router
from app.api.resumes import router as resumes_router
from app.api.screening import public_router as screening_public_router
from app.api.screening import router as screening_router
from app.api.staff import router as staff_router
from app.api.templates import router as templates_router
from app.api.usage import router as usage_router
from app.core.config import settings
from app.core.database import close_mongo, connect_to_mongo, ensure_indexes, wait_for_mongo
from app.core.exceptions import AppError
from app.core.logging import setup_logging
from app.core.rate_limit import client_key
from app.services.staff_service import ensure_bootstrap_admin

setup_logging()
logger = logging.getLogger(__name__)

# Fallback `code` values for errors that come from FastAPI/Starlette itself
# (404 for unknown routes, 405, 429 from the rate limiter, ...).
HTTP_ERROR_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting %s | env=%s | docs=%s",
        settings.app_name,
        settings.environment,
        f"{settings.api_prefix}/docs" if not settings.is_production else "disabled",
    )
    client = await connect_to_mongo()
    app.state.mongo = client
    db = client[settings.mongo_db_name]
    await wait_for_mongo(db)
    await ensure_indexes(db)
    await ensure_bootstrap_admin(db)

    # Background jobs are opt-in; the worker polls the persistent queue.
    worker_task: asyncio.Task | None = None
    from app.core.handlers import register_default_handlers

    register_default_handlers()
    if settings.jobs_enabled:
        from app.core.jobs import job_worker

        worker_task = asyncio.create_task(job_worker.run_forever(db))
        logger.info("Background job worker started")
    try:
        yield
    finally:
        if worker_task is not None:
            from app.core.jobs import job_worker

            job_worker.stop()
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task
        await close_mongo(getattr(app.state, "mongo", None))
        app.state.mongo = None
        logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="AI-powered mock interview platform",
    lifespan=lifespan,
    # The interactive API reference is a development aid; keep it out of
    # production so the deployed surface is not self-documented.
    docs_url=None if settings.is_production else f"{settings.api_prefix}/docs",
    redoc_url=None if settings.is_production else f"{settings.api_prefix}/redoc",
    openapi_url=None if settings.is_production else f"{settings.api_prefix}/openapi.json",
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def bind_usage_context(request: Request, call_next):
    """Expose the request's database to LLM usage recording (Phase 9).

    The LLM client is a process-wide singleton with no request context; this
    binds the acting request's database (and resets it afterwards) so token
    usage is attributed to the request that triggered it.
    """
    from app.core.usage import usage_actor, usage_db

    client = getattr(request.app.state, "mongo", None)
    db_token = usage_db.set(client[settings.mongo_db_name] if client is not None else None)
    actor_token = usage_actor.set(None)
    try:
        return await call_next(request)
    finally:
        usage_actor.reset(actor_token)
        usage_db.reset(db_token)


@app.middleware("http")
async def reject_oversized_bodies(request: Request, call_next):
    """Refuse huge bodies before they are read into memory."""
    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > settings.max_body_bytes:
        limit_mb = settings.max_body_bytes // (1024 * 1024)
        return JSONResponse(
            status_code=413,
            content={
                "detail": f"Request body exceeds the {limit_mb}MB limit.",
                "code": "payload_too_large",
            },
        )
    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """One structured line per request: id, method, path, status, duration.

    The id is minted here and echoed as `X-Request-ID` so a client report can
    be matched to the exact log line. Headers and bodies are never logged.
    """
    request_id = uuid.uuid4().hex
    method = request.method
    path = request.url.path
    client_ip = client_key(request)
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.warning(
            "%s %s failed after %sms (%s)",
            method,
            path,
            duration_ms,
            type(exc).__name__,
            extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "status_code": 500,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "exception": type(exc).__name__,
            },
        )
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    extra = {
        "request_id": request_id,
        "method": method,
        "path": path,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
        "client_ip": client_ip,
    }
    if response.status_code >= 500:
        logger.error(
            "%s %s -> %s (%sms)",
            method,
            path,
            response.status_code,
            duration_ms,
            extra=extra,
        )
    else:
        logger.info(
            "%s %s -> %s (%sms)",
            method,
            path,
            response.status_code,
            duration_ms,
            extra=extra,
        )
    return response


# Added last so CORS stays the outermost middleware and every response
# (including errors from the middleware above) carries CORS headers.
# The SPA authenticates with a Bearer header (never cookies), so credentialed
# CORS stays off and only the methods/headers the frontend sends are allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


def _error_response(
    status_code: int,
    detail: object,
    code: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    response_headers = dict(headers or {})
    if status_code == 401:
        response_headers.setdefault("WWW-Authenticate", "Bearer")
    return JSONResponse(
        status_code=status_code,
        content={"detail": jsonable_encoder(detail), "code": code},
        headers=response_headers,
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning(
        "AppError %s on %s %s: %s",
        exc.status_code,
        request.method,
        request.url.path,
        exc.message,
    )
    return _error_response(exc.status_code, exc.message, exc.code)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning(
        "Validation error on %s %s: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return _error_response(422, exc.errors(), "validation_error")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Same envelope as `AppError` for framework-raised errors."""
    code = HTTP_ERROR_CODES.get(exc.status_code, "http_error")
    return _error_response(exc.status_code, exc.detail, code, headers=exc.headers)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _error_response(500, "Internal server error", "internal_error")


app.include_router(auth_router, prefix=f"{settings.api_prefix}/auth", tags=["auth"])
app.include_router(resumes_router, prefix=f"{settings.api_prefix}/resumes", tags=["resumes"])
app.include_router(
    job_descriptions_router,
    prefix=f"{settings.api_prefix}/job-descriptions",
    tags=["job descriptions"],
)
app.include_router(jobs_router, prefix=f"{settings.api_prefix}/jobs", tags=["jobs"])
app.include_router(
    templates_router, prefix=f"{settings.api_prefix}/templates", tags=["templates"]
)
app.include_router(staff_router, prefix=f"{settings.api_prefix}/staff", tags=["staff"])
app.include_router(
    audit_router, prefix=f"{settings.api_prefix}/audit-logs", tags=["audit"]
)
app.include_router(
    screening_router, prefix=f"{settings.api_prefix}/invitations", tags=["invitations"]
)
app.include_router(
    screening_public_router, prefix=f"{settings.api_prefix}/screening", tags=["screening"]
)
app.include_router(
    api_keys_router, prefix=f"{settings.api_prefix}/api-keys", tags=["api keys"]
)
app.include_router(
    public_router, prefix=f"{settings.api_prefix}/public", tags=["public api"]
)
app.include_router(usage_router, prefix=f"{settings.api_prefix}/usage", tags=["usage"])
app.include_router(
    compliance_router, prefix=f"{settings.api_prefix}/compliance", tags=["compliance"]
)
app.include_router(
    interviews_router, prefix=f"{settings.api_prefix}/interviews", tags=["interviews"]
)
app.include_router(questions_router, prefix=f"{settings.api_prefix}/questions", tags=["questions"])
app.include_router(agui_router, prefix=f"{settings.api_prefix}/agui", tags=["ag-ui"])
app.include_router(dashboard_router, prefix=f"{settings.api_prefix}/dashboard", tags=["dashboard"])


@app.get(f"{settings.api_prefix}/health", tags=["health"])
async def health_check(request: Request) -> JSONResponse:
    """Liveness + readiness probe: reports unhealthy when MongoDB is down."""
    status_code = 200
    payload: dict[str, str] = {"status": "ok", "environment": settings.environment}
    try:
        client = getattr(request.app.state, "mongo", None)
        if client is None:
            raise RuntimeError("client not initialised")
        await client.admin.command("ping")
        payload["database"] = "ok"
    except Exception:
        logger.exception("Health check failed: database unreachable")
        status_code = 503
        payload["status"] = "degraded"
        payload["database"] = "unreachable"
    return JSONResponse(status_code=status_code, content=payload)
