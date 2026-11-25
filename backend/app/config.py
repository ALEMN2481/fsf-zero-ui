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

    # Gmail (Paso 08B, D7). Cliente OAuth web de Google: mismos valores que supabase/.env.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    gmail_redirect_uri: str = "http://localhost:8000/gmail/callback"
    gmail_return_url: str = "co.finanzassinfiltro.fsfapp://gmail-connected"
    gmail_pubsub_topic: str = ""  # projects/<id>/topics/gmail-fsf
    # Token OIDC de los avisos de Pub/Sub: cuenta de servicio emisora y audiencia (URL del endpoint push).
    pubsub_push_service_account: str = ""
    pubsub_push_audience: str = ""


settings = Settings()
