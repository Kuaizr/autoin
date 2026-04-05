from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cross-platform runtime settings shared by Linux and Windows nodes."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AUTOIN_",
        extra="ignore",
    )

    env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    redis_host: str = Field(...)
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_password: SecretStr | None = Field(default=None)
    redis_db: int = Field(default=0, ge=0)
    redis_stream_key: str = Field(default="autoin:stream:events")
    redis_task_stream_key: str = Field(default="autoin:stream:tasks")
    redis_dead_letter_stream_key: str = Field(default="autoin:stream:dead-letter")
    redis_pubsub_channel: str = Field(default="autoin:channel:events")
    redis_consumer_group: str = Field(default="autoin:group:coordinator")
    ui_lock_key: str = Field(default="autoin:lock:ui")
    ui_lock_ttl_ms: int = Field(default=15000, ge=1000)
    ui_lock_retry_delay_ms: int = Field(default=250, ge=50)
    ui_lock_retry_limit: int = Field(default=20, ge=1)

    @property
    def redis_url(self) -> str:
        password = ""
        if self.redis_password and self.redis_password.get_secret_value():
            password = f":{self.redis_password.get_secret_value()}@"
        return f"redis://{password}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
