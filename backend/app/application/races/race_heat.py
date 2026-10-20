"""O CALOR do dia da prova — quanto a previsão do tempo costuma custar no ritmo.

Corredor perde ritmo com calor e umidade (e mais ainda quem não se aclimatou): a faixa
ideal fica em torno de 10–15 °C e, daí pra cima, o custo cresce. A tabela abaixo é uma
ESTIMATIVA de treinador (não medida do atleta) sobre a SENSAÇÃO térmica média da janela
em que ele estará correndo — por isso a mensagem sempre diz "costuma custar ~X%".

A previsão vem do Open-Meteo (grátis, sem chave) e só existe a ~14 dias da prova; antes
disso o atleta segue com o "clima típico" do dossiê da prova. O lugar é a cidade do
dossiê da prova (geocodificada); sem ela, a região onde o atleta corre (início do treino
mais recente). Sem previsão ou sem lugar → None e a estratégia sai sem a linha de calor.
Ver [[race_strategy_engine]]."""

from __future__ import annotations

import math

from app.core.clock import today_local

# a previsão só é confiável (e publicada) a esta distância da prova
HORIZON_DAYS = 14

# sensação térmica média (°C) até o limite -> custo no ritmo (%)
_TIERS = ((16, 0.0), (20, 1.0), (24, 2.5), (28, 4.5), (32, 7.0))

_BEYOND_PCT = 9.0

# a partir daqui o aviso deixa de ser de ajuste e vira de segurança
STRONG_HEAT_PCT = 7.0

_DEFAULT_START_HOUR = 7


def heat_penalty_pct(feels_c: float | None) -> float:
    """Quanto o calor costuma custar no ritmo (%), pela sensação térmica média."""

    if feels_c is None:

        return 0.0

    for limit, pct in _TIERS:

        if feels_c <= limit:

            return pct

    return _BEYOND_PCT


def _start_hour(intel: dict | None) -> int:
    """Hora de largada do dossiê da prova ("07:00"); 7h quando não há."""

    raw = (intel or {}).get("start_time") or ""

    try:

        hour = int(str(raw).split(":")[0])

    except (ValueError, TypeError):

        return _DEFAULT_START_HOUR

    return hour if 0 <= hour <= 23 else _DEFAULT_START_HOUR


class RaceHeat:

    @staticmethod
    async def for_race(runner, goal, history, total_minutes: float) -> dict | None:
        """{"temp","feels","humidity","hour","where","penalty_pct"} da janela de
        prova, ou None (longe demais, sem lugar, sem previsão, qualquer falha)."""

        try:

            if goal.race_date is None:

                return None

            days = (goal.race_date - today_local()).days

            if not 0 <= days <= HORIZON_DAYS:

                return None

            from app.application.races.race_intel_service import RaceIntelService
            from app.infrastructure.integrations.weather.open_meteo_client import (
                OpenMeteoClient,
            )

            intel = RaceIntelService.for_runner(runner)

            city = (intel or {}).get("city")

            where = city

            coords = await OpenMeteoClient.geocode(city) if city else None

            if coords is None:

                from app.application.planner.daily_training_notifier import (
                    DailyTrainingNotifier,
                )

                coords = DailyTrainingNotifier._latest_coords(history)

                where = "sua região"

            if coords is None:

                return None

            hour = _start_hour(intel)

            window = max(1, min(4, math.ceil(total_minutes / 60)))

            forecast = await OpenMeteoClient.forecast_on(
                *coords, goal.race_date, start_hour=hour, hours=window,
            )

            if forecast is None:

                return None

            return {
                **forecast,
                "hour": hour,
                "where": where,
                "penalty_pct": heat_penalty_pct(forecast["feels"]),
            }

        except Exception as e:  # noqa: BLE001

            print(f"Calor da prova falhou: {e}")

            return None
