from __future__ import annotations

from datetime import date

from app.application.history.weekly_buckets import group_by_week, last_week_keys
from app.core.clock import now_local
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.garmin_health_repository import (
    GarminHealthRepository,
)
from app.infrastructure.persistence.race_prediction_repository import (
    RacePredictionRepository,
)

_RUN_HINT = ("run", "corrida", "trail")


def _is_run(sport: str) -> bool:

    s = (sport or "").lower()

    return any(h in s for h in _RUN_HINT)


class EvolutionBuilder:
    """Enriquece a tela de Evolução: jornada (km/treinos/maior), volume por
    semana (gráfico), VO2max + projeções de prova e FC de repouso. Leituras
    baratas (arquivo local + garmin health + previsão), sem IA."""

    @staticmethod
    def build(profile: str, weeks: int = 10) -> dict:

        runs = [
            a
            for a in ActivityArchiveRepository().load_activities(profile)
            if _is_run(a.sport)
        ]

        return {
            "journey": EvolutionBuilder._journey(runs),
            "weekly_volume": EvolutionBuilder._weekly_volume(runs, weeks),
            "fitness": EvolutionBuilder._fitness(profile),
        }

    @staticmethod
    def _journey(runs: list) -> dict:

        if not runs:

            return {"km_total": 0, "runs": 0, "biggest_km": 0, "since": None}

        km = [a.distance / 1000 for a in runs]

        since = min(a.start_date.date() for a in runs)

        return {
            "km_total": round(sum(km)),
            "runs": len(runs),
            "biggest_km": round(max(km), 1),
            "since": since.isoformat(),
        }

    @staticmethod
    def _weekly_volume(runs: list, weeks: int) -> list[dict]:

        buckets = group_by_week(runs)

        keys = last_week_keys(now_local().date(), weeks)

        out = []

        for y, w in keys:

            monday = date.fromisocalendar(y, w, 1)

            km = sum(a.distance for a in buckets.get((y, w), [])) / 1000

            out.append(
                {
                    "label": f"{monday.day:02d}/{monday.month:02d}",
                    "km": round(km, 1),
                }
            )

        return out

    @staticmethod
    def _fitness(profile: str) -> dict:

        snaps = GarminHealthRepository().load(profile)

        health = snaps[-1] if snaps else None

        pred = RacePredictionRepository().load(profile)
        has_pred = pred and pred.has_data

        # tendências recentes (janela de ~21 dias com dado): direção do que
        # importa pra FORMA — VO2max subindo, FC de repouso caindo, HRV subindo
        # = evoluindo. Direção crua ("up"/"down"/"flat"); o app pinta o tom.
        recent = snaps[-21:]

        hrv = None

        if health:

            hrv = health.hrv_weekly_avg or health.hrv_last_night

        return {
            "vo2max": health.vo2max if health else None,
            "vo2max_trend": EvolutionBuilder._trend(recent, "vo2max"),
            "resting_hr": health.resting_hr if health else None,
            "resting_hr_trend": EvolutionBuilder._trend(recent, "resting_hr"),
            "hrv": hrv,
            "hrv_trend": EvolutionBuilder._trend(recent, "hrv_weekly_avg")
            or EvolutionBuilder._trend(recent, "hrv_last_night"),
            "hrv_status": health.hrv_status if health else None,
            "training_status": health.training_status if health else None,
            "projection_5k": pred.time_5k if has_pred else None,
            "projection_10k": pred.time_10k if has_pred else None,
            "projection_half": pred.time_half if has_pred else None,
            "projection_marathon": pred.time_marathon if has_pred else None,
        }

    @staticmethod
    def _trend(snaps: list, attr: str) -> str | None:
        """Direção de uma métrica ao longo dos snapshots: compara a média do
        início da janela com a do fim. 'up'/'down'/'flat', ou None se faltam
        pontos. Direção CRUA (sem juízo de bom/ruim) — o app interpreta."""

        vals = [
            getattr(s, attr) for s in snaps if getattr(s, attr, None) is not None
        ]

        if len(vals) < 4:

            return None

        third = max(1, len(vals) // 3)

        early = sum(vals[:third]) / third

        late = sum(vals[-third:]) / third

        if early == 0:

            return None

        delta = (late - early) / abs(early)

        if delta > 0.02:

            return "up"

        if delta < -0.02:

            return "down"

        return "flat"
