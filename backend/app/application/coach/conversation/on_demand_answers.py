from app.application.coach.conversation.intent_router import (
    ChatIntent,
)
from app.application.orchestrators.last_training_report import (
    LastTrainingReport,
)
from app.application.planner.current_plan_provider import (
    CurrentPlanProvider,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.domain.entities.runner_profile import RunnerProfile


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

            return WeeklyPlanMessageFormatter.next_session_message(
                runner.name,
                plan,
            )

        return None
