"""Ponto ÚNICO do retrato "como você está": carrega os eixos irmãos (corpo &
carga + forma) e devolve o material pronto pro writer compor o panorama.

Reaproveita os serviços de cada eixo (não recalcula): o do corpo (que também
GRAVA o snapshot canônico do dia e compara com o histórico) e o da forma
(veredito triangulado de evolução). Assim chat sob demanda e resumo de domingo
veem exatamente a mesma leitura. Ver [[StatePortraitWriter]] e
[[project_ideias_produto]] #21."""

from datetime import date

from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
)
from app.application.coach.intelligence.fitness_reading_service import (
    FitnessReadingService,
)
from app.domain.entities.body_reading import BodyReading
from app.domain.entities.fitness_evolution import FitnessEvolution


class StatePortraitService:

    @staticmethod
    def read(
        profile: str,
        reference_date: date | None = None,
        persist: bool = True,
    ) -> tuple[BodyReading, FitnessEvolution]:
        """Corpo (com gravação do snapshot, igual à leitura avulsa) + forma. A
        trajetória do corpo é computada/persistida pelo serviço do corpo, mas o
        retrato não a narra (o panorama é crisp; o detalhe vive nas avulsas)."""

        reading, _trajectory = BodyReadingService.read(
            profile, reference_date=reference_date, persist=persist
        )

        evolution = FitnessReadingService.read_evolution(
            profile, reference_date=reference_date
        )

        return reading, evolution
