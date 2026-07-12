import json

from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


class PushedPlanStore:
    """Snapshot do ÚLTIMO plano que foi empurrado pro Garmin — com os
    registros de push (workout_id/schedule_id/fingerprint) por sessão.

    `push_current_plan` reconcilia o plano ATUAL contra ESTE snapshot, não
    contra si mesmo. Sem isso, REGENERAR o plano perdia o rastro do que já
    estava no relógio: o re-push empurrava os novos e deixava os antigos
    órfãos (duplicata com nomenclatura velha). Com o snapshot, o reconciliador
    troca/remove só os NOSSOS treinos (os que têm workout_id guardado) — treino
    de OUTRA fonte (outro app/treinador) nunca é tocado, porque não temos
    registro dele."""

    @staticmethod
    def _file(profile: str):

        return GarminClient.token_dir(profile) / "pushed_plan.json"

    @staticmethod
    def load(profile: str) -> TrainingPlan | None:

        file = PushedPlanStore._file(profile)

        if not file.exists():

            return None

        with open(file, encoding="utf-8") as f:

            return WeeklyPlanRepository._from_dict(json.load(f))

    @staticmethod
    def save(profile: str, plan: TrainingPlan) -> None:

        file = PushedPlanStore._file(profile)

        file.parent.mkdir(parents=True, exist_ok=True)

        with open(file, "w", encoding="utf-8") as f:

            json.dump(
                WeeklyPlanRepository._to_dict(plan),
                f,
                ensure_ascii=False,
                indent=2,
            )
