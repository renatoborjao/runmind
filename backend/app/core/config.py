from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==========================
    # APP
    # ==========================

    app_name: str = "runmind-api"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = False

    host: str = "0.0.0.0"
    port: int = 8000

    # URL pública da API (usada em links enviados ao corredor,
    # ex: OAuth do Strava). Em produção vem do .env.
    public_base_url: str = "http://127.0.0.1:8000"

    # ==========================
    # CORS
    # ==========================

    cors_origins: str = "http://localhost:3000"

    # ==========================
    # SUPABASE
    # ==========================

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # ==========================
    # STRAVA
    # ==========================

    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_refresh_token: str = ""

    # ==========================
    # EVOLUTION
    # ==========================

    evolution_api_url: str = ""
    evolution_api_key: str = ""
    evolution_instance: str = ""

    # desliga o canal WhatsApp inteiro (envio + watchdog) quando a
    # instância Evolution está fora do ar — evita erro a cada 5 min
    whatsapp_enabled: bool = True

    # ==========================
    # TELEGRAM
    # ==========================

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    # ==========================
    # GOOGLE GEMINI
    # ==========================

    google_api_key: str = ""

    # A cota gratuita é POR MODELO: conversa num modelo, extrações
    # estruturadas (parser/memória/resumo/plano) noutro mais leve —
    # separa os orçamentos e as extrações não roubam cota do chat.
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_extract_model: str = "gemini-2.5-flash-lite"

    @property
    def cors_origin_list(self) -> list[str]:

        return [

            origin.strip()

            for origin in self.cors_origins.split(",")

            if origin.strip()

        ]


@lru_cache
def get_settings() -> Settings:

    return Settings()