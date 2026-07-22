from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field


@dataclass(slots=True)
class RunnerProfile:

    id: str

    name: str

    age: int

    weight: float

    height: float

    phone: str

    goal: str

    weekly_training_days: int

    preferred_running_days: list[str] = field(
        default_factory=list
    )

    strength_training_days: list[str] = field(
        default_factory=list
    )

    # Preferência do atleta: dia em que gosta de fazer o longão (ex.:
    # "Sunday"). Fixa o longão nesse dia se for dia de treino; None =
    # o planejador decide (fim de semana por padrão).
    preferred_long_run_day: str | None = None

    target_race: str | None = None

    target_time: str | None = None

    # Data da prova alvo (ISO). Opcional: só existe se o atleta tiver
    # prova — registrada naturalmente pela conversa ou onboarding.
    race_date: str | None = None

    # ID do atleta no Strava.
    # Será utilizado pelo webhook para identificar
    # automaticamente o corredor.
    strava_athlete_id: int | None = None

    injuries: list[str] = field(
        default_factory=list
    )

    # Autodeclarados no onboarding; usados como fallback de métricas
    # enquanto não há histórico do Strava.
    initial_pace_min_km: float | None = None

    initial_weekly_km: float | None = None

    # Capacidade de quem ainda não corre (extraída do texto livre no
    # onboarding). Guia a trilha run/walk até o Strava trazer dados reais.
    #   mobility: "walker" (só caminha) | "run_walker" (trote+caminhada) |
    #             "runner" (já corre contínuo, pouco) | None
    mobility: str | None = None

    # Quanto tempo (min) consegue correr sem parar; walk pace declarado.
    continuous_run_minutes: float | None = None

    walk_pace_min_km: float | None = None

    # Retrato-base importado de um plano do atleta (ex.: plano gerado por
    # outra IA acompanhando a evolução dele). Quando o histórico do Strava
    # é fino/incompleto, isto vira o PISO do baseline — o motor planeja
    # nesse nível em vez de subestimar. Chaves: weekly_km, runs_per_week,
    # typical_km, longest_km.
    plan_baseline: dict | None = None

    # Tem treinador humano: o RunMind só acompanha os treinos enviados
    # (print/foto/PDF), nunca gera nem ajusta plano.
    external_coach: bool = False

    # Canal de mensagens do atleta e endereço nativo do Telegram.
    # "whatsapp" usa `phone`; "telegram" usa `telegram_id` (chat_id).
    channel: str = "whatsapp"

    telegram_id: str | None = None

    # Fuso horário do atleta (IANA, ex.: "Europe/Lisbon"). Guia as datas do
    # coach (hoje/amanhã, semana) e o horário dos disparos. Default Brasil;
    # ajustável por atleta (ex.: amigo em Portugal).
    timezone: str = "America/Sao_Paulo"

    # Sexo biológico ("M"/"F") — usado no cálculo de carga por FC (TRIMP de
    # Banister tem fator diferente por sexo). None = desconhecido (a carga cai
    # no %FCR linear). Coletado no onboarding.
    sex: str | None = None