import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ExternalServiceError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from app.db.base import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: confirm DB connection
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection confirmed.")
    except Exception as exc:
        logger.warning("Database connection failed: %s — app will start without DB.", exc)
    yield
    # Shutdown
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Rayna Product Automation API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler for custom exceptions
    @app.exception_handler(NotFoundError)
    @app.exception_handler(UnauthorizedError)
    @app.exception_handler(ForbiddenError)
    @app.exception_handler(ConflictError)
    @app.exception_handler(BadRequestError)
    @app.exception_handler(ExternalServiceError)
    async def custom_exception_handler(request: Request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "1.0.0"}

    # Register v1 routers
    from app.api.v1.routes import router as v1_router
    app.include_router(v1_router, prefix="/api/v1")

    return app


app = create_app()
