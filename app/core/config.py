from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DATABASE_URL: str = "postgresql://postgres.rzcddtooxikqudursqaj:DAWER%21%21%40%40%23%23@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"
    JWT_SECRET_KEY: str = "supersecretkeychangeinproduction1234567890"
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "daweros-api"
    JWT_AUDIENCE: str = "daweros-users"
    CORS_ORIGINS: list[str] = ["*"]
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()