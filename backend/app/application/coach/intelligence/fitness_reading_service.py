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
from app.application.history.fitness_evolution_analyzer import (
    FitnessEvolutionAnalyzer,
)
from app.domain.entities.aerobic_efficiency import AerobicEfficiency
from app.domain.entities.fitness_evolution import FitnessEvolution
from app.domain.value_objects.sports import is_run_sport
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
        """Só a eficiência aeróbica (EF) — sinal isolado. Mantido pra quem quer
        exatamente esse eixo; o veredito completo vive em `read_evolution`."""

        activities, series, resting_hr, max_hr = (
            FitnessReadingService._load(profile)
        )

        return AerobicEfficiencyAnalyzer.analyze(
            activities,
            reference_date=reference_date,
            resting_hr=resting_hr,
            max_hr=max_hr,
        )

    @staticmethod
    def read_evolution(
        profile: str,
        reference_date: date | None = None,
    ) -> FitnessEvolution:
        """Veredito COMPLETO do "estou evoluindo?": EF curto+longo + VO₂máx +
        FC-repouso, cada um só quando tem lastro."""

        activities, series, resting_hr, max_hr = (
            FitnessReadingService._load(profile)
        )

        return FitnessEvolutionAnalyzer.analyze(
            activities,
            series,
            reference_date=reference_date,
            resting_hr=resting_hr,
            max_hr=max_hr,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _load(profile: str):
        """Matéria-prima comum: atividades arquivadas + série de saúde + FC de
        repouso (mediana) e FC máx (Tanaka) — igual ao BodyReadingBuilder."""

        activities = ActivityArchiveRepository().load_activities(profile)

        series = GarminHealthRepository().load(profile)

        runner = RunnerProfileRepository().load(profile)

        resting_hr = FitnessReadingService._resting_hr(series)

        max_hr = FitnessReadingService._max_hr(
            getattr(runner, "age", None), activities
        )

        return activities, series, resting_hr, max_hr

    # ------------------------------------------------------------------

    @staticmethod
    def _resting_hr(series) -> int | None:
        """FC de repouso = mediana da série de saúde (robusta a dia atípico).
        Mesma regra do BodyReadingBuilder — os dois eixos usam o mesmo número."""

        values = [h.resting_hr for h in series if h.resting_hr is not None]

        return round(statistics.median(values)) if values else None

    # FC máx plausível de corrida (descarta sensor travado/erro de leitura)
    _MAX_HR_FLOOR = 150
    _MAX_HR_CEILING = 215

    @staticmethod
    def _max_hr(age, activities) -> int | None:
        """FC máxima: prefere a MEDIDA (maior FC máx real vista em corrida, um
        dado do próprio atleta) à estimada por idade (Tanaka subestima muita
        gente). Usa o MAIOR entre a observada e a de Tanaka — a observada é um
        piso real do teto verdadeiro; Tanaka cobre quem nunca foi ao máximo.
        Sem nenhum dos dois → None (o analisador só fica mais ruidoso)."""

        tanaka = round(208 - 0.7 * age) if age and age > 0 else None

        observed = FitnessReadingService._observed_max_hr(activities)

        candidates = [v for v in (tanaka, observed) if v is not None]

        return max(candidates) if candidates else None

    @staticmethod
    def _observed_max_hr(activities) -> int | None:
        """Maior FC máx plausível registrada em corrida — o teto REAL já visto.
        Filtra faixa plausível pra um pico de sensor não inflar."""

        peaks = [
            a.max_heartrate
            for a in activities
            if is_run_sport(a.sport)
            and a.max_heartrate
            and FitnessReadingService._MAX_HR_FLOOR
            <= a.max_heartrate
            <= FitnessReadingService._MAX_HR_CEILING
        ]

        return round(max(peaks)) if peaks else None
