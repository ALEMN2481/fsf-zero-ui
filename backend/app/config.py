from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    supabase_url: str = ""
    supabase_anon_key: str = ""  # clave pública; la service_role no se usa en este backend todavía


settings = Settings()
