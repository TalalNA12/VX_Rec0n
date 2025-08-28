# backend/app/core/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Read .env and ignore any unknown keys so you don't crash
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",            # <-- important: don't error on extra keys
    )

    # Core settings
    DATABASE_URL: str = "postgresql+psycopg://vx:vxpass@localhost:5432/vx_recon"
    FRONTEND_ORIGIN: str = "http://127.0.0.1:5173"

    # You had these in your .env — define them here so they're allowed
    SECRET_KEY: str = "change-me"
    NIKTO_IMAGE: str = "ghcr.io/sullo/nikto:latest"

settings = Settings()
