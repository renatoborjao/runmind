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
from app.application.coach.writer.body_reading_writer import BodyReadingWriter
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

        all_snapshots = repo.load(profile)

        prior = [s for s in all_snapshots if s.day < today]

        trajectory = BodyTrajectoryAnalyzer.of(prior, reading, today)

        # só guarda leitura com dado de recuperação de verdade — snapshot sem
        # corpo não ajuda a comparar nada
        if persist and reading.recovery.has_data:

            # preserva a narrativa já cacheada hoje (se o estado não mudou) —
            # sem isso, toda releitura no dia (ex.: chat) apagaria o cache e
            # forçaria a IA a rodar de novo na próxima abertura da tela
            today_snapshot = (
                all_snapshots[-1]
                if all_snapshots and all_snapshots[-1].day == today
                else None
            )

            narrative = (
                today_snapshot.narrative
                if today_snapshot and today_snapshot.body_state == reading.body_state
                else None
            )

            repo.record(
                profile,
                BodyReadingService.snapshot_of(
                    reading, now_local(), narrative=narrative
                ),
            )

        return reading, trajectory

    @staticmethod
    async def narrative_for(
        profile: str,
        runner_name: str,
        reading: BodyReading,
        trajectory: BodyTrajectory,
        reference_date: date | None = None,
    ) -> str | None:
        """Narrativa da IA pra leitura de HOJE, com cache de 1 geração por dia
        (telas home/corpo chamam isso a cada abertura — sem cache seria 1
        chamada Gemini por load). None quando não há recuperação de verdade
        (sem Garmin/carga insuficiente): nada honesto pra narrar ainda.

        Cache vive no MESMO snapshot diário do histórico de trajetória — se já
        existe um snapshot de hoje com narrativa, reusa; senão gera (IA, com
        fallback determinístico do BodyReadingWriter) e só GRAVA no cache
        quando veio da IA de verdade (fallback não trava o dia: a próxima
        abertura tenta a IA de novo)."""

        if not reading.recovery.has_data:

            return None

        today = reference_date or today_local()

        repo = BodyReadingHistoryRepository()

        snapshots = repo.load(profile)

        today_snapshot = snapshots[-1] if snapshots and snapshots[-1].day == today else None

        if (
            today_snapshot is not None
            and today_snapshot.narrative
            and today_snapshot.body_state == reading.body_state
        ):

            return today_snapshot.narrative

        narrative, from_ai = await BodyReadingWriter.narrate(
            reading, runner_name, trajectory
        )

        if from_ai:

            repo.record(
                profile,
                BodyReadingService.snapshot_of(
                    reading, now_local(), narrative=narrative
                ),
            )

        return narrative

    @staticmethod
    def snapshot_of(
        reading: BodyReading, at, narrative: str | None = None
    ) -> BodyReadingSnapshot:
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
            narrative=narrative,
        )
