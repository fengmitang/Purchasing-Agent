"""Application assembly for the modular monolith."""

from fastapi import FastAPI

from app.api.health import router as health_router
from app.shared.constants import APP_NAME, APP_VERSION


def create_application() -> FastAPI:
    """Build a new FastAPI application instance."""
    application = FastAPI(title=APP_NAME, version=APP_VERSION)
    application.include_router(health_router)
    return application
