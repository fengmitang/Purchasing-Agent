"""Database readiness probe used by later HTTP readiness checks."""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine


async def database_is_ready(engine: AsyncEngine) -> bool:
    """Return whether a lightweight database query succeeds."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True
