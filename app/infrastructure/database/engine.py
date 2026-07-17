"""Async SQLAlchemy engine construction."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import Settings


def create_database_engine(settings: Settings) -> AsyncEngine:
    """Create an async engine without opening a database connection."""
    return create_async_engine(
        settings.sqlalchemy_database_url,
        pool_pre_ping=True,
    )
