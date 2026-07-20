from app.application.coach.conversation.goal_change_detector import (
    GoalChangeDetector,
)
from app.application.onboarding.onboarding_answer_parser import (
    OnboardingAnswerParser,
)
from app.application.planner.current_plan_provider import CurrentPlanProvider
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


class GoalChangeApplier:
    """Fluxo reativo de troca de OBJETIVO: o atleta pede pra mudar a meta
    no chat (texto livre, com ou sem prova/data/tempo-alvo). Aplica DE
    VERDADE na hora — sem confirmação, igual à preferência de dia do
    longão — e regera o plano da semana já com a meta nova."""

    @staticmethod
    async def handle(
        profile: str,
        runner: RunnerProfile,
        incoming_text: str,
    ) -> str | None:

        if not GoalChangeDetector.looks_like_goal_change(incoming_text):

            return None

        extracted = await OnboardingAnswerParser.parse(
            step="ASK_GOAL",
            question="Qual é o objetivo agora?",
            answer=incoming_text,
        )

        goal = str(extracted.get("goal") or "").strip()

        # a IA concluiu que a mensagem não é de fato uma declaração de
        # objetivo (portão barato deu falso positivo) — segue o fluxo normal
        if not goal:

            return None

        updates = {"goal": goal}

        # prova/data/tempo só entram se vieram citados nesta mensagem — não
        # apaga o que já estava registrado (mesmo padrão do sync de prova
        # via memória, RunnerMemoryService._sync_race)
        if extracted.get("target_race"):

            updates["target_race"] = extracted["target_race"]

        if extracted.get("target_time"):

            updates["target_time"] = extracted["target_time"]

        if extracted.get("race_date"):

            updates["race_date"] = extracted["race_date"]

        RunnerProfileRepository().update_fields(profile, updates)

        # treinador humano: RunMind só acompanha o plano dele, não gera
        if runner.external_coach:

            return f"Anotado! Atualizei seu objetivo pra: {goal}. 🎯"

        _, plan = await CurrentPlanProvider.for_profile(
            profile,
            force=True,
        )

        plan_text = WeeklyPlanMessageFormatter.week_plan_message(
            runner.name,
            plan,
        )

        return (
            f"Fechou, {runner.name}! Atualizei seu objetivo pra: {goal}. 🎯 "
            f"Já ajustei o plano da semana pra essa meta nova.\n\n{plan_text}"
        )
