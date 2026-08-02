"""Orquestra a leitura de SONO como eixo próprio: carrega a série de saúde do
Garmin e devolve o SleepReading (média/tendência/regularidade/dívida). Fino de
propósito — a ciência mora no analisador puro. Ver [[SleepReadingAnalyzer]]."""

from datetime import date

from app.application.history.sleep_reading_analyzer import (
    SleepReadingAnalyzer,
)
from app.domain.entities.sleep_reading import SleepReading
from app.infrastructure.persistence.garmin_health_repository import (
    GarminHealthRepository,
)


class SleepReadingService:

    @staticmethod
    def read(
        profile: str,
        reference_date: date | None = None,
    ) -> SleepReading:

        series = GarminHealthRepository().load(profile)

        return SleepReadingAnalyzer.analyze(series, reference_date)
