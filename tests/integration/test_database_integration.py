import asyncio
import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    database_is_ready,
    session_scope,
    transaction_scope,
)

pytestmark = pytest.mark.integration


def require_test_database_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for MySQL integration tests")
    return database_url


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    settings = Settings(database_url=require_test_database_url(), _env_file=None)
    database_engine = create_database_engine(settings)
    yield database_engine
    await database_engine.dispose()


@pytest_asyncio.fixture
async def transaction_probe_table(engine: AsyncEngine) -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE IF EXISTS issue2_transaction_probe"))
        await connection.execute(
            text(
                "CREATE TABLE issue2_transaction_probe ("
                "id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, "
                "value VARCHAR(64) NOT NULL"
                ") ENGINE=InnoDB"
            )
        )
    yield
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE IF EXISTS issue2_transaction_probe"))


@pytest.mark.asyncio
async def test_database_probe_succeeds(engine: AsyncEngine) -> None:
    assert await database_is_ready(engine) is True


@pytest.mark.asyncio
async def test_sessions_use_distinct_connections(engine: AsyncEngine) -> None:
    session_factory = create_session_factory(engine)

    async with session_scope(session_factory) as first, session_scope(session_factory) as second:
        first_id, second_id = await asyncio.gather(
            first.scalar(text("SELECT CONNECTION_ID()")),
            second.scalar(text("SELECT CONNECTION_ID()")),
        )

    assert first_id != second_id


@pytest.mark.asyncio
async def test_transaction_scope_commits(
    engine: AsyncEngine,
    transaction_probe_table: None,
) -> None:
    session_factory = create_session_factory(engine)

    async with transaction_scope(session_factory) as session:
        await session.execute(
            text("INSERT INTO issue2_transaction_probe (value) VALUES ('committed')")
        )

    async with session_scope(session_factory) as session:
        count = await session.scalar(text("SELECT COUNT(*) FROM issue2_transaction_probe"))

    assert count == 1


@pytest.mark.asyncio
async def test_transaction_scope_rolls_back_on_error(
    engine: AsyncEngine,
    transaction_probe_table: None,
) -> None:
    session_factory = create_session_factory(engine)

    with pytest.raises(RuntimeError, match="force rollback"):
        async with transaction_scope(session_factory) as session:
            await session.execute(
                text("INSERT INTO issue2_transaction_probe (value) VALUES ('rolled-back')")
            )
            raise RuntimeError("force rollback")

    async with session_scope(session_factory) as session:
        count = await session.scalar(text("SELECT COUNT(*) FROM issue2_transaction_probe"))

    assert count == 0


async def get_table_names(database_url: str) -> set[str]:
    settings = Settings(database_url=database_url, _env_file=None)
    engine = create_database_engine(settings)
    try:
        async with engine.connect() as connection:
            table_names = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_table_names()
            )
    finally:
        await engine.dispose()
    return set(table_names)


def test_empty_database_migration_has_one_head(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = require_test_database_url()
    monkeypatch.setenv("DATABASE_URL", database_url)
    alembic_config = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_config)

    assert script.get_heads() == ["0001_database_baseline"]

    command.upgrade(alembic_config, "head")
    assert asyncio.run(get_table_names(database_url)) == {"alembic_version"}

    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
