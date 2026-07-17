"""Environment-backed application configuration."""

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    """Validated settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: SecretStr

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        """Require a complete SQLAlchemy URL using the asyncmy driver."""
        try:
            url = make_url(value.get_secret_value())
        except ArgumentError:
            raise ValueError("DATABASE_URL must be a valid SQLAlchemy URL") from None

        if url.drivername != "mysql+asyncmy":
            raise ValueError("DATABASE_URL must use the mysql+asyncmy driver")
        if not url.username or not url.password:
            raise ValueError("DATABASE_URL must include a username and password")
        if not url.host or not url.database:
            raise ValueError("DATABASE_URL must include a host and database name")
        return value

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return the secret URL only at the database integration boundary."""
        return self.database_url.get_secret_value()
