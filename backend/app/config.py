from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./backend/vocal_biomarkers.db"
    app_api_token: str = "development-token"
    amplifier_base_url: str = "https://api.amplifierhealth.com"
    amplifier_account_id: str = ""
    amplifier_api_key: str = ""
    amplifier_webhook_secret: str = ""
    cors_origin: str = "http://127.0.0.1:4173"
    stream_ticket_ttl_seconds: int = 120
    pulse_poll_seconds: float = 3.0
    pulse_max_attempts: int = 2


@lru_cache
def settings() -> Settings:
    return Settings()
