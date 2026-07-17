import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_require_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "database_url, expected_message",
    [
        ("not-a-url", "valid SQLAlchemy URL"),
        ("mysql+pymysql://user:password@localhost/database", "mysql\\+asyncmy"),
        ("mysql+asyncmy://localhost/database", "username and password"),
        ("mysql+asyncmy://user:@localhost/database", "username and password"),
        ("mysql+asyncmy://user:password@localhost", "host and database name"),
    ],
)
def test_settings_reject_invalid_database_urls(
    database_url: str,
    expected_message: str,
) -> None:
    with pytest.raises(ValidationError, match=expected_message):
        Settings(database_url=database_url, _env_file=None)


def test_settings_hide_database_credentials_in_errors() -> None:
    invalid_url = "postgresql://private_user:super-secret@localhost/database"

    with pytest.raises(ValidationError) as error:
        Settings(database_url=invalid_url, _env_file=None)

    assert "private_user" not in str(error.value)
    assert "super-secret" not in str(error.value)


def test_settings_accept_asyncmy_database_url() -> None:
    database_url = "mysql+asyncmy://user:password@localhost/database?charset=utf8mb4"

    settings = Settings(database_url=database_url, _env_file=None)

    assert settings.sqlalchemy_database_url == database_url
    assert "password" not in repr(settings.database_url)
