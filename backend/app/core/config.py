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
    # WHATSAPP
    # ==========================

    # qual driver de WhatsApp usar: "evolution" (não-oficial, Baileys) ou
    # "cloud" (Cloud API oficial da Meta). A lógica do coach não muda; só
    # troca quem entrega/recebe a mensagem.
    whatsapp_provider: str = "evolution"

    # desliga o canal WhatsApp inteiro (envio + watchdog) quando o driver
    # está fora do ar — evita erro repetido no scheduler
    whatsapp_enabled: bool = True

    # --- Evolution (não-oficial) ---
    evolution_api_url: str = ""
    evolution_api_key: str = ""
    evolution_instance: str = ""

    # --- Cloud API oficial da Meta ---
    # token permanente (System User) — Graph API
    whatsapp_cloud_token: str = ""
    # id do número registrado (Phone Number ID)
    whatsapp_phone_number_id: str = ""
    # id da conta comercial (WhatsApp Business Account ID)
    whatsapp_business_account_id: str = ""
    # segredo do app — valida a assinatura do webhook (X-Hub-Signature-256)
    whatsapp_app_secret: str = ""
    # token que NÓS definimos, conferido na verificação do webhook (GET)
    whatsapp_verify_token: str = ""
    # versão da Graph API nas chamadas
    whatsapp_graph_version: str = "v21.0"

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
    # Aliases flutuantes ("-latest"): o Google aposentou o
    # gemini-2.5-flash e TODA análise caiu no fallback silenciosamente;
    # o alias acompanha o flash estável e não some debaixo de nós.
    gemini_chat_model: str = "gemini-flash-latest"
    gemini_extract_model: str = "gemini-flash-lite-latest"
    # Cérebro do coach (plano + análise): modelo mais forte, pro raciocínio
    # que define a qualidade. Alias flutuante do Pro (mesma lógica do flash).
    # ATENÇÃO: o Pro NÃO desliga thinking (min 128, cobrado como output) —
    # quem usa este modelo tem que passar thinking_budget>0 E max_output_tokens
    # com folga pra caber thinking + resposta (senão volta vazio).
    gemini_coach_model: str = "gemini-pro-latest"

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