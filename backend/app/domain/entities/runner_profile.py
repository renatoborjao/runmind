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

    # Tem treinador humano: o RunMind só acompanha os treinos enviados
    # (print/foto/PDF), nunca gera nem ajusta plano.
    external_coach: bool = False

    # Canal de mensagens do atleta e endereço nativo do Telegram.
    # "whatsapp" usa `phone`; "telegram" usa `telegram_id` (chat_id).
    channel: str = "whatsapp"

    telegram_id: str | None = None