from __future__ import annotations

from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")
    database_url: str = Field(alias="DATABASE_URL")
    bot_master_key: str = Field(alias="BOT_MASTER_KEY")
    admin_telegram_id: int = Field(alias="ADMIN_TELEGRAM_ID")
    secret_ttl_seconds: int = Field(default=45, alias="SECRET_TTL_SECONDS")
    notify_hour_utc: int = Field(default=9, alias="NOTIFY_HOUR_UTC")

    @field_validator("secret_ttl_seconds")
    @classmethod
    def validate_ttl(cls, value: int) -> int:
        if value < 10 or value > 300:
            raise ValueError("SECRET_TTL_SECONDS должен быть в диапазоне 10..300")
        return value

    @field_validator("notify_hour_utc")
    @classmethod
    def validate_notify_hour(cls, value: int) -> int:
        if value < 0 or value > 23:
            raise ValueError("NOTIFY_HOUR_UTC должен быть в диапазоне 0..23")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
