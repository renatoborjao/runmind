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
    # VOZ (áudio)
    # ==========================

    # Transcrição LOCAL das notas de voz do atleta (faster-whisper, Whisper
    # da OpenAI, MIT). Roda em CPU/ARM, grátis e self-hosted — o áudio nunca
    # sai da máquina. O texto transcrito entra no MESMO pipeline de conversa
    # que o coach já entende. "base" equilibra qualidade x custo em CPU;
    # "small" é mais preciso e mais pesado. Ver [[project_ideias_produto]].
    whisper_model: str = "base"

    # áudio acima disso (segundos) o coach pede pra escrever, em vez de
    # gastar CPU transcrevendo um monólogo
    voice_max_seconds: int = 300

    # Motor de TTS quando o COACH fala (voz -> áudio). "gemini" = Gemini TTS
    # (mesmo Google que já usamos; voz natural, teste cego escolheu a Charon
    # calorosa — o edge-tts grátis saiu robótico demais); "edge" = edge-tts
    # (fallback grátis/externo). Trocável por config sem retrabalho. Falha de
    # TTS nunca vira silêncio — a mensagem sai em texto do mesmo jeito.
    voice_engine: str = "gemini"

    # Gemini TTS: modelo + voz + estilo (o estilo guia a entonação; a Charon
    # com tom de treinador brasileiro caloroso foi a escolhida no teste cego).
    voice_gemini_model: str = "gemini-3.1-flash-tts-preview"
    voice_gemini_voice: str = "Charon"
    voice_gemini_style: str = (
        "Fale como um treinador brasileiro próximo e caloroso, num tom de "
        "conversa espontânea de manhã, ritmo fluido e natural, sem soar "
        "leitura: "
    )

    # voz pt-BR do edge-tts (fallback)
    voice_edge_voice: str = "pt-BR-AntonioNeural"

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

    # Cérebro coach que aprende com o resultado: a destilação semanal e a
    # gravação/debug rodam SEMPRE; esta flag controla só a INJEÇÃO dos
    # aprendizados no prompt do plano. Fica DESLIGADA até validar o que o
    # cérebro aprendeu (modo observação via GET /debug/learnings/{profile}).
    coach_learning_inject_enabled: bool = False

    # Trajetória do corpo (foto -> filme): a gravação do histórico, a
    # trajetória e o fato pro cérebro rodam SEMPRE. Esta flag controla só se a
    # frase de trajetória entra na MENSAGEM que o atleta recebe. Fica DESLIGADA
    # até validar no /debug/body-trajectory/{profile} (modo observação).
    body_trajectory_in_message_enabled: bool = False

    # Vigia de prontidão: a avaliação e o diário (GET /debug/readiness) rodam
    # SEMPRE (observação). Esta flag controla só o ENVIO proativo dos alertas
    # de prontidão (atenção/sinal verde) ao atleta. Fica DESLIGADA até validar
    # o diário nos atletas reais. A sobrecarga (STRAINED) já é tratada pela
    # proposta do BodyConductProposer no despertar — o vigia cobre a lacuna
    # (CAUTION/GREEN).
    readiness_alerts_enabled: bool = False

    # Cérebro do coach na conversa: UM coach só, sempre respondendo, com o
    # quadro completo do atleta — decide (responder/propor mudança/aplicar) numa
    # chamada estruturada e as "mãos" determinísticas executam. Fica DESLIGADA
    # até validar OFFLINE contra os prints reais + canário no perfil do Renato;
    # com a flag OFF, roda a cascata determinística estável de sempre (fallback).
    # Ver [[project_roteador_acao_ia]] e [[feedback_nao_tapar_sol_com_peneira]].
    coach_brain_enabled: bool = False

    # Canário: quando não-vazio, o cérebro roda SÓ pra estes perfis (ex.:
    # "renato2"), mesmo com coach_brain_enabled=true. Vazio = todos os perfis
    # (quando a flag global estiver ligada). Perfis separados por vírgula.
    coach_brain_profiles: str = ""

    @property
    def coach_brain_profile_list(self) -> list[str]:

        return [p.strip() for p in self.coach_brain_profiles.split(",") if p.strip()]

    def coach_brain_active_for(self, profile: str) -> bool:
        """O cérebro atende este perfil? (flag global + allowlist de canário)."""

        if not self.coach_brain_enabled:

            return False

        allow = self.coach_brain_profile_list

        return not allow or profile in allow

    # Governador de proativos: portão único por onde passa tudo que o coach
    # INICIA (briefing, review, prova, re-engajamento, recap, empurrões). Dá
    # diário unificado + teto diário (isentando os essenciais) + dedup entre
    # fontes — ataca a família de bugs de proativo repetido/fora de hora/
    # empilhado. OFF = passthrough (comportamento de hoje, sem diário).
    # Ver [[project_governador_proativos]].
    proactive_governor_enabled: bool = False

    # Canário: quando não-vazio, o governador atua SÓ nestes perfis (ex.:
    # "renato2"), mesmo com a flag global ligada. Vazio = todos.
    proactive_governor_profiles: str = ""

    # Teto de mensagens PROATIVAS não-essenciais por atleta/dia (essenciais —
    # análise pós-treino, dia da prova, recorde — são ISENTOS). Renato: 2/dia.
    proactive_daily_budget: int = 2

    @property
    def proactive_governor_profile_list(self) -> list[str]:

        return [
            p.strip()
            for p in self.proactive_governor_profiles.split(",")
            if p.strip()
        ]

    def proactive_governor_active_for(self, profile: str) -> bool:
        """O governador atua neste perfil? (flag global + allowlist de canário)."""

        if not self.proactive_governor_enabled:

            return False

        allow = self.proactive_governor_profile_list

        return not allow or profile in allow

    # Conversas de RECONCILIAÇÃO do coach (perguntas que fecham lacunas): quando
    # o atleta treina em ROTINA além dos dias registrados, o coach pergunta se
    # quer oficializar mais um dia; e quando a META está vaga (sem prova/prazo),
    # pede pra cravar. Uma vez só (dedup), governado, orientar-não-repetir.
    # DESLIGADA até validar offline + o Renato liberar. Ver
    # [[project_reconciliacao_coach]] e [[feedback_orientar_nao_mandar]].
    coach_reconcile_enabled: bool = False

    # Canário: quando não-vazio, roda SÓ nestes perfis. Vazio = todos (com a
    # flag global ligada). Perfis separados por vírgula.
    coach_reconcile_profiles: str = ""

    @property
    def coach_reconcile_profile_list(self) -> list[str]:

        return [
            p.strip()
            for p in self.coach_reconcile_profiles.split(",")
            if p.strip()
        ]

    def coach_reconcile_active_for(self, profile: str) -> bool:
        """As conversas de reconciliação atendem este perfil? (flag + canário)."""

        if not self.coach_reconcile_enabled:

            return False

        allow = self.coach_reconcile_profile_list

        return not allow or profile in allow

    # METAS/PROVAS pelo cérebro do coach: quando ligada, a ação `goal` do
    # CoachBrain traz os campos ESTRUTURADOS da prova (nome/distância/data ISO/
    # tempo-alvo/relação degrau×norte) e um executor determinístico aplica com a
    # âncora certa (prova datada MAIS PRÓXIMA nunca é atropelada por uma mais
    # distante), preserva o objetivo-mãe e grava a hierarquia na memória. OFF =
    # roteia pro GoalChangeApplier de sempre (fallback estável). Canário no
    # renato2 até validar offline. Ver [[project_multiplos_objetivos]].
    goal_brain_enabled: bool = False

    goal_brain_profiles: str = ""

    @property
    def goal_brain_profile_list(self) -> list[str]:

        return [
            p.strip()
            for p in self.goal_brain_profiles.split(",")
            if p.strip()
        ]

    def goal_brain_active_for(self, profile: str) -> bool:
        """O executor estruturado de metas/provas atende este perfil?
        (flag global + allowlist de canário)."""

        if not self.goal_brain_enabled:

            return False

        allow = self.goal_brain_profile_list

        return not allow or profile in allow

    # MODELO PRO só na geração do PLANO da semana (a tarefa de raciocínio mais
    # pesada, roda 1×/semana/atleta — então mesmo um modelo caro sai barato). O
    # resto (chat/briefing/análise/memória) segue no Flash, rápido e barato onde
    # é frequente. Canário; fallback Pro→Flash→determinístico se o Pro cair/
    # rate-limit. Validado offline (A/B nos dados reais). Ver [[project_consumo_tokens]].
    plan_model_enabled: bool = False

    plan_model_profiles: str = ""

    # modelo forte usado na geração do plano quando a flag está ativa pro perfil
    plan_model: str = "gemini-3.1-pro-preview"

    # orçamento de raciocínio (thinking) do plano no modelo forte
    plan_thinking_budget: int = 8192

    @property
    def plan_model_profile_list(self) -> list[str]:

        return [
            p.strip()
            for p in self.plan_model_profiles.split(",")
            if p.strip()
        ]

    def plan_model_active_for(self, profile: str) -> bool:
        """O plano deste perfil usa o modelo PRO? (flag global + canário)."""

        if not self.plan_model_enabled:

            return False

        allow = self.plan_model_profile_list

        return not allow or profile in allow

    # RENOMEAR O TREINO NO STRAVA com o nome do nosso plano (ex.: "Tempo 6 km")
    # no lugar do genérico "Corrida matinal". Exige escopo activity:write (o
    # atleta reconecta o Strava uma vez). Canário: começa só no renato2 pra
    # teste. Ver [[project_tracker_tenis]] / roadmap.
    strava_rename_enabled: bool = False

    strava_rename_profiles: str = ""

    @property
    def strava_rename_profile_list(self) -> list[str]:

        return [
            p.strip()
            for p in self.strava_rename_profiles.split(",")
            if p.strip()
        ]

    def strava_rename_active_for(self, profile: str) -> bool:
        """Renomear o treino no Strava atende este perfil? (flag + canário)."""

        if not self.strava_rename_enabled:

            return False

        allow = self.strava_rename_profile_list

        return not allow or profile in allow

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