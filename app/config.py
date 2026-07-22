"""Environment-backed application configuration."""

from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class RuntimeSettings(BaseSettings):
    """Process settings that are safe to load before integrations initialize."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        """Accept conventional case-insensitive log-level names."""
        return value.upper() if isinstance(value, str) else value


class Settings(RuntimeSettings):
    """Validated integration settings loaded from environment or a local .env file."""

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


class AgentSettings(RuntimeSettings):
    """Optional Agent runtime settings; missing configuration keeps chat safely disabled."""

    agent_enabled: bool = False
    agent_provider: Literal["anthropic", "openai"] = "anthropic"
    agent_model: str = "claude-3-5-sonnet-20241022"
    agent_api_key: SecretStr | None = None
    agent_base_url: str | None = None
    agent_timeout_seconds: float = 15.0
    agent_max_retries: int = 1
    agent_redis_url: SecretStr | None = None
    agent_session_ttl_seconds: int = 604_800
    agent_allow_in_memory: bool = False

    @field_validator("agent_timeout_seconds")
    @classmethod
    def validate_agent_timeout(cls, value: float) -> float:
        if value <= 0 or value > 120:
            raise ValueError("AGENT_TIMEOUT_SECONDS must be between 0 and 120")
        return value

    @field_validator("agent_max_retries")
    @classmethod
    def validate_agent_retries(cls, value: int) -> int:
        if value < 0 or value > 3:
            raise ValueError("AGENT_MAX_RETRIES must be between 0 and 3")
        return value
