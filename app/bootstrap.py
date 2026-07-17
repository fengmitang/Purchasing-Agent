"""Application assembly for the modular monolith."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.health import router as health_router
from app.api.middleware import RequestContextMiddleware
from app.config import RuntimeSettings
from app.infrastructure.logging import configure_logging
from app.shared.constants import APP_NAME, APP_VERSION
from app.shared.errors import DomainError
from app.shared.exception_handlers import (
    domain_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)


def create_application() -> FastAPI:
    """Build a new FastAPI application instance."""
    runtime_settings = RuntimeSettings()
    configure_logging(runtime_settings.log_level)
    application = FastAPI(title=APP_NAME, version=APP_VERSION)
    application.add_middleware(RequestContextMiddleware)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(DomainError, domain_exception_handler)
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.include_router(health_router)
    return application
