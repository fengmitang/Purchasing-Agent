from contextlib import AbstractAsyncContextManager
from typing import cast

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.config import Settings
from app.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    database_is_ready,
    make_session_dependency,
    session_scope,
)


@pytest.mark.asyncio
async def test_session_factory_creates_isolated_sessions() -> None:
    settings = Settings(
        database_url="mysql+asyncmy://user:password@localhost/database",
        _env_file=None,
    )
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)

    async with session_scope(session_factory) as first, session_scope(session_factory) as second:
        assert first is not second

    await engine.dispose()


@pytest.mark.asyncio
async def test_session_dependency_creates_a_new_session_per_call() -> None:
    settings = Settings(
        database_url="mysql+asyncmy://user:password@localhost/database",
        _env_file=None,
    )
    engine = create_database_engine(settings)
    dependency = make_session_dependency(create_session_factory(engine))

    first_iterator = dependency()
    second_iterator = dependency()
    first = await anext(first_iterator)
    second = await anext(second_iterator)

    assert first is not second

    await first_iterator.aclose()
    await second_iterator.aclose()
    await engine.dispose()


class FailingConnectionContext(AbstractAsyncContextManager[AsyncConnection]):
    async def __aenter__(self) -> AsyncConnection:
        raise SQLAlchemyError("database unavailable")

    async def __aexit__(self, *args: object) -> None:
        return None


class FailingEngine:
    def connect(self) -> FailingConnectionContext:
        return FailingConnectionContext()


@pytest.mark.asyncio
async def test_database_probe_returns_false_for_sqlalchemy_errors() -> None:
    engine = cast(AsyncEngine, FailingEngine())

    assert await database_is_ready(engine) is False
