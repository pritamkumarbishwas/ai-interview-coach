import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.job_descriptions import router as job_descriptions_router
from app.api.resumes import router as resumes_router
from app.core.config import settings
from app.core.database import close_mongo, connect_to_mongo, ensure_indexes
from app.core.exceptions import AppError
from app.core.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting %s | env=%s | docs=%s",
        settings.app_name,
        settings.environment,
        settings.api_prefix + "/docs",
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
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    openapi_url=f"{settings.api_prefix}/openapi.json",
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning(
        "Validation error on %s %s: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors()), "code": "validation_error"},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "internal_error"},
    )


app.include_router(auth_router, prefix=f"{settings.api_prefix}/auth", tags=["auth"])
app.include_router(resumes_router, prefix=f"{settings.api_prefix}/resumes", tags=["resumes"])
app.include_router(
    job_descriptions_router,
    prefix=f"{settings.api_prefix}/job-descriptions",
    tags=["job descriptions"],
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
