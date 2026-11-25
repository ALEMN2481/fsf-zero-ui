from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env, aunque se arranque desde otra carpeta.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    app_env: str = "dev"
    supabase_url: str = ""
    # Clave pública; la service_role no se usa en este backend todavía.
    supabase_anon_key: str = ""


settings = Settings()
