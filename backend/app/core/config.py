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

    # Telegram chat_id do DONO (Renato) pra alertas operacionais — quando o
    # coach falha várias vezes seguidas, o backend avisa aqui em vez de a
    # falha morrer no log até alguém testar por acaso. Vazio = alertas OFF
    # (nada é enviado, nunca quebra). Setar ADMIN_TELEGRAM_ID no .env.
    admin_telegram_id: str = ""

    # ==========================
    # GOOGLE GEMINI
    # ==========================

    google_api_key: str = ""

    # A cota é POR MODELO: conversa num modelo, extrações estruturadas
    # (parser/memória/resumo/plano) noutro mais leve — separa os
    # orçamentos e as extrações não roubam cota do chat.
    #
    # VERSÕES PINADAS (não os aliases "-latest"). Fomos pinado→flutuante→
    # pinado: pinar na 2.5 pegou a aposentadoria dela; migrar pro "-latest"
    # trocou por um risco pior — o alias mudou de versão SOZINHO (2026-07) e
    # começou a rejeitar thinking_budget=0 com 400, derrubando o bot inteiro
    # da noite pro dia, sem aviso ([[project_gemini_alias_thinking_bug]]).
    # Versão pinada some só quando o Google APOSENTA, o que é ANUNCIADO com
    # meses de antecedência — falha agendada e avisada, não silenciosa às 23h.
    # Escolha (2026-07-22): melhor flash GA disponível — teste cego com o
    # retrato real do Renato mostrou o 3.6-flash claramente acima do 3.5
    # (estrutura completa em toda sessão, personalização, coerência com a
    # meta), e o 3.5-flash vinha INDISPONÍVEL (respostas caindo no lite).
    # Todo Pro segue preview (cota free apertada + aposentadoria sem aviso);
    # promover quando existir Pro GA. Ao promover, conferir o catálogo vivo
    # (client.models.list) e o retirement schedule; o piso de thinking do
    # gemini/client.py protege budget=0 mesmo se um modelo novo o rejeitar.
    #
    # Chat = coach de propósito: a conversa É o produto ("conversa viva"),
    # merece o melhor modelo; cota free do flash comporta o volume atual e o
    # fallback pro lite segura estouro. Extração fica num lite (tarefa de
    # parsing, não precisa do topo) SEPARADO, pra não roubar cota do chat.
    gemini_chat_model: str = "gemini-3.6-flash"
    gemini_extract_model: str = "gemini-3.5-flash-lite"
    # Cérebro do coach (plano + análise): melhor modelo ESTÁVEL disponível.
    # (O gemini/client.py já cuida da folga de thinking no max_output_tokens
    # e do piso do budget — os chamadores dimensionam só a SAÍDA.)
    gemini_coach_model: str = "gemini-3.6-flash"

    # ==========================
    # BACKUP DO STORAGE
    # ==========================

    # snapshot .zip periódico do storage/ (dados dos atletas). backup_dir
    # vazio = backend/backups (mesmo disco: protege contra corrupção/
    # exclusão). Aponte pra uma pasta do OneDrive/Google Drive pra ter
    # cópia FORA da máquina de graça. keep = quantos snapshots manter.
    backup_enabled: bool = True
    backup_dir: str = ""
    backup_keep: int = 28

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