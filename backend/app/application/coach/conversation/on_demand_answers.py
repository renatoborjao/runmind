from app.application.coach.conversation.intent_router import (
    ChatIntent,
)
from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
)
from app.application.coach.writer.body_reading_writer import (
    BodyReadingWriter,
)
from app.application.orchestrators.last_training_report import (
    LastTrainingReport,
)
from app.application.planner.current_plan_provider import (
    CurrentPlanProvider,
)
from app.application.planner.weekly_plan_matcher import (
    WeeklyPlanMatcher,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.config import get_settings
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_load import LOAD_INSUFFICIENT


class OnDemandAnswers:
    """Respostas canônicas e completas para perguntas com dado pronto no
    sistema — devolvidas sem passar pelo Gemini, para não resumir nem
    desconfigurar. None = não há resposta determinística (segue no chat)."""

    @staticmethod
    async def answer(
        intent: ChatIntent,
        profile: str,
        runner: RunnerProfile,
    ) -> str | None:

        if intent == ChatIntent.LAST_TRAINING:

            # None quando não há treino registrado — cai no Gemini, que
            # responde com naturalidade a partir do contexto.
            return await LastTrainingReport.build(profile)

        if intent == ChatIntent.NEXT_TRAINING:

            _, plan = await CurrentPlanProvider.for_profile(profile)

            # pula as sessões já cumpridas (mesmo fora de ordem)
            history = await LoadTrainingHistory.execute(profile=profile)

            done_days = WeeklyPlanMatcher.fulfilled_days(
                plan,
                history.activities,
            )

            return WeeklyPlanMessageFormatter.next_session_message(
                runner.name,
                plan,
                done_days=done_days,
            )

        if intent == ChatIntent.WEEKLY_PLAN:

            _, plan = await CurrentPlanProvider.for_profile(profile)

            # valida contra o histórico real: o que foi de fato treinado
            # aparece como feito; o resto do passado, como não feito
            history = await LoadTrainingHistory.execute(profile=profile)

            done_days = WeeklyPlanMatcher.fulfilled_days(
                plan,
                history.activities,
            )

            return WeeklyPlanMessageFormatter.week_plan_message(
                runner.name,
                plan,
                done_days=done_days,
            )

        if intent == ChatIntent.BODY_READING:

            # o service lê o corpo E grava/compara com o histórico (trajetória)
            reading, trajectory = BodyReadingService.read(profile)

            # sem recuperação (não tem Garmin) E sem carga suficiente: não há
            # leitura útil — cai no Gemini, que responde com naturalidade
            if (
                not reading.recovery.has_data
                and reading.load.status == LOAD_INSUFFICIENT
            ):

                return None

            # a trajetória só entra na MENSAGEM atrás da flag (modo observação);
            # a gravação já aconteceu independente disso
            note = (
                trajectory
                if get_settings().body_trajectory_in_message_enabled
                else None
            )

            return await BodyReadingWriter.write(
                reading, runner.name, trajectory=note
            )

        return None
