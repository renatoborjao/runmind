"""Celebração de PR/marcos: depois de cada treino concluído, verifica se o
atleta bateu um recorde real (corrida mais longa, treino mais rápido numa
faixa de distância, marco de km acumulado, semana de maior volume) e devolve
UMA mensagem comemorativa (ou None). NUNCA muda o plano — é puro
reconhecimento, igual pra atleta RunMind ou de treinador externo.

Cold start: no primeiro treino processado de um atleta (ou logo após esta
feature subir), TUDO seria "recorde" — por isso a primeira chamada apenas
semeia as melhores marcas conhecidas e não comemora nada. Só a partir da
segunda chamada os recordes passam a valer."""

from app.application.history.runner_metrics import (
    RUN_MIN_DISTANCE_KM,
    WALK_PACE_CUTOFF,
)
from app.application.history.weekly_buckets import group_by_week
from app.application.planner.pace_formatter import PaceFormatter
from app.domain.entities.enriched_activity import EnrichedActivity
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory
from app.infrastructure.persistence.personal_record_repository import (
    PersonalRecordRepository,
)

_LONGEST_MIN_KM = 3.0

_BANDS = [
    (3.0, 5.0, "3-5"),
    (5.0, 8.0, "5-8"),
    (8.0, 12.0, "8-12"),
    (12.0, 18.0, "12-18"),
    (18.0, None, "18+"),
]

# margem mínima pra contar como PR de pace (evita disparo por ruído de GPS
# ou micro-melhora imperceptível): ~3s/km
_PACE_MARGIN_MIN_KM = 0.05

_KM_MILESTONES = [100, 250, 500, 1000, 1500, 2000, 3000, 5000]


class PersonalRecordDetector:

    @staticmethod
    def after_feedback(
        runner: RunnerProfile,
        history: TrainingHistory,
        enriched: EnrichedActivity,
    ) -> str | None:

        repo = PersonalRecordRepository()

        records = repo.load(runner.id)

        if not records.get("seeded"):

            repo.save(
                runner.id,
                PersonalRecordDetector._seed(history),
            )

            return None

        wins: list[str] = []

        activity = enriched.activity

        dist_km = activity.distance / 1000

        # -- corrida mais longa ------------------------------------------
        longest_km = records.get("longest_km", 0.0)

        if (
            activity.sport == "Run"
            and dist_km >= _LONGEST_MIN_KM
            and dist_km > longest_km
        ):

            wins.append(
                f"🏆 sua corrida mais longa até hoje: {dist_km:.1f} km!"
            )

            records["longest_km"] = round(dist_km, 2)

        # -- treino mais rápido na faixa -----------------------------------
        pace = PersonalRecordDetector._pace(activity)

        band = PersonalRecordDetector._band(dist_km)

        if (
            band is not None
            and pace is not None
            and dist_km >= RUN_MIN_DISTANCE_KM
            and pace <= WALK_PACE_CUTOFF
        ):

            pace_by_band = records.setdefault("pace_by_band", {})

            best = pace_by_band.get(band)

            if best is None or best - pace >= _PACE_MARGIN_MIN_KM:

                wins.append(
                    "⚡ seu treino mais rápido na faixa de "
                    f"{band} km: pace {PaceFormatter.format(pace)}/km!"
                )

                pace_by_band[band] = round(pace, 2)

        # -- marco de km acumulado ------------------------------------------
        total_km = history.total_distance / 1000

        milestone_before = records.get("total_km_milestone", 0)

        crossed = [
            m for m in _KM_MILESTONES
            if milestone_before < m <= total_km
        ]

        if crossed:

            milestone = max(crossed)

            wins.append(f"🎉 você passou de {milestone} km com o RunMind!")

            records["total_km_milestone"] = milestone

        # -- semana de maior volume ------------------------------------------
        week_result = PersonalRecordDetector._week_record(
            history,
            records,
        )

        if week_result:

            wins.append(week_result)

        repo.save(runner.id, records)

        if not wins:

            return None

        return PersonalRecordDetector._message(runner.name, wins)

    @staticmethod
    def _seed(history: TrainingHistory) -> dict:

        records: dict = {"seeded": True}

        runs = [
            a for a in history.activities
            if a.sport == "Run" and a.distance / 1000 >= _LONGEST_MIN_KM
        ]

        if runs:

            records["longest_km"] = round(
                max(a.distance for a in runs) / 1000,
                2,
            )

        pace_by_band: dict[str, float] = {}

        for activity in history.activities:

            dist_km = activity.distance / 1000

            pace = PersonalRecordDetector._pace(activity)

            band = PersonalRecordDetector._band(dist_km)

            if (
                band is None
                or pace is None
                or dist_km < RUN_MIN_DISTANCE_KM
                or pace > WALK_PACE_CUTOFF
            ):

                continue

            if band not in pace_by_band or pace < pace_by_band[band]:

                pace_by_band[band] = round(pace, 2)

        if pace_by_band:

            records["pace_by_band"] = pace_by_band

        total_km = history.total_distance / 1000

        crossed = [m for m in _KM_MILESTONES if m <= total_km]

        if crossed:

            records["total_km_milestone"] = max(crossed)

        buckets = group_by_week(history.activities)

        if buckets:

            best_key = max(buckets)

            best_km = sum(
                a.distance for a in buckets[best_key]
            ) / 1000

            records["best_week_km"] = round(best_km, 2)

            records["best_week_key"] = f"{best_key[0]}-W{best_key[1]:02d}"

        return records

    @staticmethod
    def _week_record(
        history: TrainingHistory,
        records: dict,
    ) -> str | None:

        buckets = group_by_week(history.activities)

        if not buckets:

            return None

        current_key = max(buckets)

        current_km = sum(
            a.distance for a in buckets[current_key]
        ) / 1000

        current_key_str = f"{current_key[0]}-W{current_key[1]:02d}"

        best_km = records.get("best_week_km", 0.0)

        best_key = records.get("best_week_key")

        if current_km <= best_km:

            return None

        # bate o recorde de sempre; a mensagem só sai UMA vez por semana —
        # runs seguintes na MESMA semana continuam atualizando o valor por
        # baixo dos panos, sem repetir a comemoração.
        already_this_week = current_key_str == best_key

        records["best_week_km"] = round(current_km, 2)

        records["best_week_key"] = current_key_str

        if already_this_week:

            return None

        return f"📈 sua semana de maior volume: {current_km:.1f} km!"

    @staticmethod
    def _pace(activity) -> float | None:

        if activity.average_speed <= 0:

            return None

        return (1000 / activity.average_speed) / 60

    @staticmethod
    def _band(dist_km: float) -> str | None:

        for low, high, label in _BANDS:

            if high is None:

                if dist_km >= low:

                    return label

            elif low <= dist_km < high:

                return label

        return None

    @staticmethod
    def _message(name: str, wins: list[str]) -> str:

        if len(wins) == 1:

            return f"{name}, {wins[0]}"

        lines = "\n".join(f"- {w}" for w in wins)

        return f"{name}, você bateu {len(wins)} recordes hoje:\n{lines}"
