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

DEMO_TABLES = {
    "agent_message",
    "agent_session",
    "auth_session",
    "building",
    "employee",
    "employee_building_role",
    "idempotency_record",
    "operation_log",
    "product_category",
    "product_supplier",
    "product_whitelist",
    "purchase_approval",
    "purchase_order",
    "purchase_requirement",
    "purchase_status_history",
    "recommendation",
    "role",
    "supplier",
    "user_account",
    "user_login_identifier",
    "user_role",
}


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

    async with (
        session_scope(session_factory) as first,
        session_scope(session_factory) as second,
    ):
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


async def get_workflow_schema(database_url: str) -> dict[str, object]:
    settings = Settings(database_url=database_url, _env_file=None)
    engine = create_database_engine(settings)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: {
                    "employee_columns": {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("employee")
                    },
                    "requirement_columns": {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("purchase_requirement")
                    },
                    "requirement_product_name_nullable": next(
                        column["nullable"]
                        for column in inspect(sync_connection).get_columns("purchase_requirement")
                        if column["name"] == "product_name"
                    ),
                    "order_product_id_nullable": next(
                        column["nullable"]
                        for column in inspect(sync_connection).get_columns("purchase_order")
                        if column["name"] == "product_id"
                    ),
                    "idempotency_columns": {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("idempotency_record")
                    },
                    "approval_columns": {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("purchase_approval")
                    },
                    "order_columns": {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("purchase_order")
                    },
                    "history_columns": {
                        column["name"]
                        for column in inspect(sync_connection).get_columns(
                            "purchase_status_history"
                        )
                    },
                    "account_columns": {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("user_account")
                    },
                    "session_columns": {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("auth_session")
                    },
                    "requirement_foreign_tables": {
                        foreign_key["referred_table"]
                        for foreign_key in inspect(sync_connection).get_foreign_keys(
                            "purchase_requirement"
                        )
                    },
                    "approval_foreign_tables": {
                        foreign_key["referred_table"]
                        for foreign_key in inspect(sync_connection).get_foreign_keys(
                            "purchase_approval"
                        )
                    },
                    "history_foreign_tables": {
                        foreign_key["referred_table"]
                        for foreign_key in inspect(sync_connection).get_foreign_keys(
                            "purchase_status_history"
                        )
                    },
                }
            )
    finally:
        await engine.dispose()


def test_empty_database_migration_has_one_head(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = require_test_database_url()
    monkeypatch.setenv("DATABASE_URL", database_url)
    alembic_config = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_config)

    assert script.get_heads() == ["0006_workflow_routing"]

    command.upgrade(alembic_config, "head")
    assert asyncio.run(get_table_names(database_url)) == DEMO_TABLES | {"alembic_version"}

    workflow_schema = asyncio.run(get_workflow_schema(database_url))
    assert {"employee_no", "name", "phone", "role", "status", "version"} <= (
        workflow_schema["employee_columns"]
    )
    assert {
        "requirement_no",
        "employee_id",
        "applicant_employee_no",
        "applicant_name",
        "applicant_phone",
        "requested_at",
        "submitted_at",
        "revision_no",
        "previous_requirement_id",
        "building_id",
        "application_reason",
        "application_location",
        "device_type",
        "product_full_name",
        "quantity_raw",
        "unit_price",
        "unit_price_raw",
        "total_amount",
        "source_reference",
        "version",
    } <= workflow_schema["requirement_columns"]
    assert workflow_schema["requirement_product_name_nullable"] is True
    assert workflow_schema["order_product_id_nullable"] is True
    assert {
        "actor_code",
        "operation",
        "idempotency_key",
        "request_hash",
        "resource_type",
        "resource_id",
        "response_payload",
        "created_at",
    } <= workflow_schema["idempotency_columns"]
    assert {
        "requirement_id",
        "approver_id",
        "approver_employee_no",
        "approver_name",
        "approver_phone",
        "action",
        "comment",
        "acted_at",
    } <= workflow_schema["approval_columns"]
    assert {
        "purchaser_id",
        "purchaser_employee_no",
        "purchaser_name",
        "purchaser_phone",
        "quoted_at",
        "contracted_at",
        "received_at",
        "completed_at",
        "version",
    } <= workflow_schema["order_columns"]
    assert {
        "requirement_id",
        "order_id",
        "from_status",
        "to_status",
        "operator_id",
        "changed_at",
    } <= workflow_schema["history_columns"]
    assert {
        "employee_id",
        "password_hash",
        "must_change_password",
        "failed_login_count",
        "locked_until",
        "last_login_at",
    } <= workflow_schema["account_columns"]
    assert {
        "account_id",
        "session_token_hash",
        "expires_at",
        "last_seen_at",
        "revoked_at",
    } <= workflow_schema["session_columns"]
    assert {
        "employee",
        "product_category",
        "product_whitelist",
        "purchase_requirement",
        "supplier",
    } <= workflow_schema["requirement_foreign_tables"]
    assert workflow_schema["approval_foreign_tables"] == {
        "employee",
        "purchase_requirement",
    }
    assert workflow_schema["history_foreign_tables"] == {
        "employee",
        "purchase_order",
        "purchase_requirement",
    }

    command.downgrade(alembic_config, "base")
    assert asyncio.run(get_table_names(database_url)) == {"alembic_version"}
    command.upgrade(alembic_config, "head")
    assert asyncio.run(get_table_names(database_url)) == DEMO_TABLES | {"alembic_version"}
