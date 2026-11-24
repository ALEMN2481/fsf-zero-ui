from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"  # backend/.env, arranque desde cualquier carpeta


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    app_env: str = "dev"
    supabase_url: str = ""
    supabase_anon_key: str = ""  # clave pública; la service_role no se usa en este backend todavía


settings = Settings()
