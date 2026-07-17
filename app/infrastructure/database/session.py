"""Async session factories and explicit transaction scopes."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

AsyncSessionFactory = async_sessionmaker[AsyncSession]
SessionDependency = Callable[[], AsyncIterator[AsyncSession]]


def create_session_factory(engine: AsyncEngine) -> AsyncSessionFactory:
    """Bind a reusable factory that creates a new session for each call."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def session_scope(session_factory: AsyncSessionFactory) -> AsyncIterator[AsyncSession]:
    """Create and close one session without committing business work."""
    async with session_factory() as session:
        try:
            yield session
        except BaseException:
            if session.in_transaction():
                await session.rollback()
            raise


@asynccontextmanager
async def transaction_scope(
    session_factory: AsyncSessionFactory,
) -> AsyncIterator[AsyncSession]:
    """Provide an explicit commit-or-rollback boundary for a business service."""
    async with session_scope(session_factory) as session, session.begin():
        yield session


def make_session_dependency(session_factory: AsyncSessionFactory) -> SessionDependency:
    """Build a FastAPI-compatible dependency that never reuses a session."""

    async def get_session() -> AsyncIterator[AsyncSession]:
        async with session_scope(session_factory) as session:
            yield session

    return get_session
