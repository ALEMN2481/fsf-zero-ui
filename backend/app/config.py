from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env, aunque se arranque desde otra carpeta.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    app_env: str = "dev"
    supabase_url: str = ""
    # Clave pública: las rutas con usuario reenvían su JWT (D4).
    supabase_anon_key: str = ""
    # Solo para la ingesta, que no tiene usuario (D4). Nunca sale del backend.
    supabase_service_role_key: str = ""
    # Claves AES-256-GCM de los correos: "versión:base64,versión:base64"; cifra la versión más alta.
    email_keys: str = ""


settings = Settings()
