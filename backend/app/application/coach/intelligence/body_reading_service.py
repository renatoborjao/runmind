"""Ponto ÚNICO de leitura do corpo com memória. Monta a leitura (builder),
compara com o histórico (trajetória) e persiste o snapshot do dia — pra que
chat sob demanda, resumo de domingo e o cérebro coach vejam a MESMA coisa.

Separado do BodyReadingBuilder (que é puro/sem escrita) de propósito: aqui é
onde a leitura ganha lado de fora (grava em disco e olha o passado)."""

from datetime import date

from app.application.coach.intelligence.body_reading_builder import (
    BodyReadingBuilder,
)
from app.application.coach.intelligence.body_trajectory_analyzer import (
    BodyTrajectoryAnalyzer,
)
from app.core.clock import now_local, today_local
from app.domain.entities.body_reading import BodyReading
from app.domain.entities.body_reading_snapshot import (
    BodyReadingSnapshot,
    BodyTrajectory,
)
from app.infrastructure.persistence.body_reading_history_repository import (
    BodyReadingHistoryRepository,
)


class BodyReadingService:

    @staticmethod
    def read(
        profile: str,
        reference_date: date | None = None,
        persist: bool = True,
    ) -> tuple[BodyReading, BodyTrajectory]:
        """Leitura do corpo + trajetória. A trajetória compara com os dias
        ANTERIORES (o snapshot de hoje é excluído da comparação e só então
        gravado), então reler no mesmo dia não muda o veredito nem duplica a
        série. `persist=False` = só lê (debug/cérebro), não escreve."""

        today = reference_date or today_local()

        reading = BodyReadingBuilder.build(profile, reference_date)

        repo = BodyReadingHistoryRepository()

        prior = [s for s in repo.load(profile) if s.day < today]

        trajectory = BodyTrajectoryAnalyzer.of(prior, reading, today)

        # só guarda leitura com dado de recuperação de verdade — snapshot sem
        # corpo não ajuda a comparar nada
        if persist and reading.recovery.has_data:

            repo.record(
                profile,
                BodyReadingService.snapshot_of(reading, now_local()),
            )

        return reading, trajectory

    @staticmethod
    def snapshot_of(reading: BodyReading, at) -> BodyReadingSnapshot:
        """Congela o essencial da leitura num snapshot. `at` é datetime (hora
        local da leitura; no backfill, o dia histórico reconstruído)."""

        rec = reading.recovery

        return BodyReadingSnapshot(
            at=at.isoformat(),
            body_state=reading.body_state,
            limiter=reading.limiter,
            acwr=reading.load.acwr,
            acwr_status=reading.load.status,
            hrv_recent=rec.hrv_recent,
            hrv_direction=rec.hrv_direction,
            rhr_recent=rec.rhr_recent,
            rhr_direction=rec.rhr_direction,
            sleep_avg_hours=rec.sleep_avg_hours,
            short_nights=rec.short_nights,
            nights_counted=rec.nights_counted,
        )
