"""Ponto ÚNICO de leitura da FORMA aeróbica (o eixo "estou evoluindo?").

Carrega o histórico de atividades + a FC de repouso/máx do atleta e entrega a
tendência de eficiência aeróbica pronta. Espelha o BodyReadingBuilder na forma
de obter FC repouso (mediana da série de saúde) e FC máx (Tanaka pela idade) —
mesmos números da leitura do corpo, pra os dois eixos falarem a mesma língua.

Fitness (isto) e recuperação/carga (leitura do corpo) são eixos IRMÃOS e
diferentes: a carga diz 'você está aguentando', isto diz 'você está
melhorando'. Ver [[project_analise_corpo_garmin]] e [[project_ideias_produto]]."""

import statistics
from datetime import date

from app.application.history.aerobic_efficiency_analyzer import (
    AerobicEfficiencyAnalyzer,
)
from app.domain.entities.aerobic_efficiency import AerobicEfficiency
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.garmin_health_repository import (
    GarminHealthRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


class FitnessReadingService:

    @staticmethod
    def read(
        profile: str,
        reference_date: date | None = None,
    ) -> AerobicEfficiency:

        activities = ActivityArchiveRepository().load_activities(profile)

        series = GarminHealthRepository().load(profile)

        runner = RunnerProfileRepository().load(profile)

        resting_hr = FitnessReadingService._resting_hr(series)

        max_hr = FitnessReadingService._max_hr(getattr(runner, "age", None))

        return AerobicEfficiencyAnalyzer.analyze(
            activities,
            reference_date=reference_date,
            resting_hr=resting_hr,
            max_hr=max_hr,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _resting_hr(series) -> int | None:
        """FC de repouso = mediana da série de saúde (robusta a dia atípico).
        Mesma regra do BodyReadingBuilder — os dois eixos usam o mesmo número."""

        values = [h.resting_hr for h in series if h.resting_hr is not None]

        return round(statistics.median(values)) if values else None

    @staticmethod
    def _max_hr(age) -> int | None:
        """FC máxima por Tanaka (208 − 0,7·idade). Sem idade → None (o
        analisador não filtra por faixa, só fica mais ruidoso)."""

        if not age or age <= 0:

            return None

        return round(208 - 0.7 * age)
