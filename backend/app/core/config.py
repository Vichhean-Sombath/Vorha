from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Vorha"
    environment: str = "development"
    database_url: str = "sqlite:///./vorha.db"
    jwt_secret_key: str = "development-only-change-this-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    redis_url: str | None = None
    frontend_url: str = "http://localhost:3000"
    telegram_client_id: str | None = None
    telegram_bot_id: str | None = None
    audio_extraction_enabled: bool = True
    audio_cache_dir: str = "./.audio-cache"
    audio_bitrate: str = "128"
    audio_max_bytes: int = 60 * 1024 * 1024
    audio_extract_timeout_seconds: float = 120.0

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @model_validator(mode="after")
    def require_production_secret(self) -> "Settings":
        if self.environment.lower() == "production" and len(self.jwt_secret_key) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 characters in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
