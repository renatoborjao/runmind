"""Re-engajamento: quando o atleta some (sem treino nem conversa há tempo demais
PRA O PADRÃO DELE), o coach vai atrás — acolhe, ancora em quem ele é e convida a
retomar. UM toque por episódio de silêncio (nunca repete).

Roda de hora em hora; cada _notify_one decide se é o horário local do atleta e
faz dedup por episódio. Fecha a peça de retenção que faltava
([[project_ideias_produto]], [[project_pendencias_abertas]])."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.application.history.silence_detector import SilenceDetector
from app.application.notifications.coach_outbox import CoachOutbox
from app.application.review.reengagement_writer import ReengagementWriter
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import LoadTrainingHistory
from app.core.clock import now_in, use_athlete_timezone
from app.infrastructure.persistence.conversation_repository import (
    ConversationRepository,
)
from app.infrastructure.persistence.dispatch_guard import DispatchGuard
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# fim de tarde local — dá a noite pro atleta agir se topar retomar hoje
REENGAGE_HOUR = 17

HISTORY_LIMIT = 60


class ReengagementNotifier:

    @staticmethod
    async def notify_all() -> None:

        for profile in RunnerProfileRepository().list_all():

            try:

                await ReengagementNotifier._notify_one(profile)

            except Exception as e:

                print(f"Falha no re-engajamento de '{profile}': {e}")

    @staticmethod
    async def _notify_one(profile: str) -> None:

        runner = LoadRunnerProfile.execute(profile)

        use_athlete_timezone(runner.timezone)

        local = now_in(runner.timezone)

        # só no fim de tarde LOCAL do atleta (o dedup por episódio impede repetir)
        if local.hour != REENGAGE_HOUR:

            return

        today = local.date()

        history = await LoadTrainingHistory.execute(
            profile=profile,
            limit=HISTORY_LIMIT,
        )

        run_dates = [a.start_date.date() for a in history.activities]

        last_inbound = ReengagementNotifier._last_inbound(profile, runner.timezone)

        verdict = SilenceDetector.assess(run_dates, last_inbound, today)

        if not verdict.is_dark:

            return

        # UM toque por episódio de silêncio: a chave muda quando o atleta dá
        # sinal de vida (treina/conversa), liberando um novo episódio no futuro.
        if DispatchGuard.already_sent("reengagement", profile, verdict.episode_key):

            return

        DispatchGuard.mark("reengagement", profile, verdict.episode_key)

        facts = ReengagementWriter.facts(
            name=runner.name,
            days_silent=verdict.days_silent,
            last_run_desc=ReengagementNotifier._last_run_desc(history, today),
            cadence_desc=ReengagementNotifier._cadence_desc(verdict.typical_gap_days),
            goal_desc=ReengagementNotifier._goal_desc(runner),
            motivation=ReengagementNotifier._motivation(profile),
            profile=profile,
        )

        message = await ReengagementWriter.write(profile, facts)

        # beat emocional (a mão estendida) — sai em texto + áudio se ele aceita voz
        await CoachOutbox.send(
            runner, message, voice=True, profile=profile, kind="reengagement",
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _last_inbound(profile: str, tz: str) -> date | None:
        """Data (local) da última mensagem que o ATLETA mandou — sinal de que
        ele estava por aqui mesmo sem treinar. None se nunca falou."""

        try:

            turns = ConversationRepository().load(profile)

        except Exception:

            return None

        for turn in reversed(turns):

            if turn.get("role") != "user":

                continue

            stamp = turn.get("timestamp")

            if not stamp:

                continue

            try:

                dt = datetime.fromisoformat(stamp)

            except ValueError:

                continue

            return dt.astimezone(ZoneInfo(tz)).date()

        return None

    @staticmethod
    def _last_run_desc(history, today: date) -> str | None:

        if not history.activities:

            return None

        last = max(history.activities, key=lambda a: a.start_date)

        km = (last.distance or 0) / 1000

        days = (today - last.start_date.date()).days

        when = "hoje" if days == 0 else ("ontem" if days == 1 else f"há {days} dias")

        if km >= 0.5:

            return f"{km:.1f} km, {when}"

        return when

    @staticmethod
    def _cadence_desc(gap_days: float) -> str | None:
        """Traduz o intervalo típico em corridas/semana, em linguagem de gente."""

        if gap_days <= 0:

            return None

        per_week = round(7 / gap_days)

        if per_week >= 5:

            return "quase todo dia"

        if per_week <= 1:

            return "cerca de 1x por semana"

        return f"cerca de {per_week}x por semana"

    @staticmethod
    def _goal_desc(runner) -> str | None:

        try:

            goal = BuildTrainingGoal.execute(runner)

            if goal is None:

                return None

            label = getattr(goal, "race_label", None)

            race_date = getattr(goal, "race_date", None) or getattr(
                runner, "race_date", None
            )

            if label and race_date:

                return f"{label} em {race_date}"

            return label

        except Exception:

            return None

    @staticmethod
    def _motivation(profile: str) -> str | None:

        try:

            from app.application.coach.memory.runner_memory_service import (
                RunnerMemoryService,
            )

            anchor = RunnerMemoryService.motivation_anchor(profile)

            return anchor or None

        except Exception:

            return None
