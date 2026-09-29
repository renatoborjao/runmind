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
from app.application.history.recovery_alert_run import RecoveryAlertRun
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

        trajectory = BodyTrajectoryAnalyzer.of(
            prior, reading, today,
            alert_since=RecoveryAlertRun.since_for_profile(profile, today),
        )

        # só guarda leitura com dado de recuperação de verdade — snapshot sem
        # corpo não ajuda a comparar nada
        if persist and reading.recovery.has_data:

            # preserva a narrativa já cacheada hoje — ela vale pela NOITE de
            # sono, não pelo estado; sem isso, toda releitura no dia (ex.: chat)
            # apagaria o cache e forçaria a IA a rodar de novo
            today_snapshot = (
                all_snapshots[-1]
                if all_snapshots and all_snapshots[-1].day == today
                else None
            )

            repo.record(
                profile,
                BodyReadingService.snapshot_of(
                    reading,
                    now_local(),
                    narrative=today_snapshot.narrative if today_snapshot else None,
                    night=today_snapshot.night if today_snapshot else None,
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
        """Narrativa da IA da leitura do corpo — UMA por noite de sono (Renato
        28/09: "deve ser alterada apenas quando recebemos os dados do sono,
        1x ao dia"). Telas home/corpo e o chat chamam isso a cada abertura;
        a IA só roda quando chega uma noite nova do relógio. Até a noite de
        hoje chegar, vale a leitura da última noite. Números que mudam durante
        o dia (a FC de repouso do Garmin é recalculada) não reescrevem nada.
        None quando não há recuperação de verdade: nada honesto pra narrar.

        O cache vive no snapshot diário do histórico de trajetória e só é
        GRAVADO quando veio da IA de verdade (fallback não trava: a próxima
        abertura tenta a IA de novo)."""

        if not reading.recovery.has_data:

            return None

        today = reference_date or today_local()

        repo = BodyReadingHistoryRepository()

        night = BodyReadingService._last_night(profile)

        cached = BodyReadingService._cached(repo.load(profile), night, today)

        if cached:

            return cached

        narrative, from_ai = await BodyReadingWriter.narrate(
            reading, runner_name, trajectory, profile=profile,
        )

        if from_ai:

            repo.record(
                profile,
                BodyReadingService.snapshot_of(
                    reading, now_local(), narrative=narrative, night=night
                ),
            )

        return narrative

    @staticmethod
    def _cached(snapshots, night: str | None, today: date) -> str | None:
        """A narrativa que ainda vale: a última escrita com a MESMA noite de
        sono. Sem sono no relógio (ou cache anterior a esta regra, sem a
        noite gravada): uma por dia."""

        written = [s for s in snapshots if s.narrative]

        if not written:

            return None

        last = written[-1]

        if night is None or last.night is None:

            return last.narrative if last.day == today else None

        return last.narrative if last.night == night else None

    @staticmethod
    def _last_night(profile: str) -> str | None:
        """Data da última noite de sono que chegou do relógio."""

        try:

            from app.infrastructure.persistence.garmin_health_repository import (
                GarminHealthRepository,
            )

            nights = [
                str(h.date)
                for h in GarminHealthRepository().load(profile)
                if h.sleep_hours is not None
            ]

            return max(nights) if nights else None

        except Exception as e:

            print(f"Noite de sono falhou p/ '{profile}': {e}")

            return None

    @staticmethod
    def snapshot_of(
        reading: BodyReading,
        at,
        narrative: str | None = None,
        night: str | None = None,
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
            night=night,
        )
