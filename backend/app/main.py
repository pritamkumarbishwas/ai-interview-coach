import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.auth import router as auth_router
from app.api.interviews import router as interviews_router
from app.api.job_descriptions import router as job_descriptions_router
from app.api.resumes import router as resumes_router
from app.core.config import settings
from app.core.database import close_mongo, connect_to_mongo, ensure_indexes
from app.core.exceptions import AppError
from app.core.logging import setup_logging

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
    await ensure_indexes(client[settings.mongo_db_name])
    try:
        yield
    finally:
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


# Added last so CORS stays the outermost middleware and every response
# (including errors from the middleware above) carries CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
app.include_router(
    interviews_router, prefix=f"{settings.api_prefix}/interviews", tags=["interviews"]
)


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
