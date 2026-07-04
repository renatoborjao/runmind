from app.application.coach.conversation.plan_preference_detector import (
    PlanPreference,
)
from app.application.planner.current_plan_provider import (
    CurrentPlanProvider,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.core.weekdays import weekday_label
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


class PlanPreferenceApplier:
    """Aplica a preferência DE VERDADE, na hora: grava no perfil, regera
    o plano da semana honrando o pedido e confirma. Atleta com treinador
    humano não tem plano gerado — só registra a preferência."""

    @staticmethod
    async def apply(
        profile: str,
        runner: RunnerProfile,
        preference: PlanPreference,
    ) -> str:

        day = preference.long_run_day

        day_label = weekday_label(day)

        # dia pedido não é um dia de treino do atleta: não força nada
        if day not in runner.preferred_running_days:

            current = ", ".join(
                weekday_label(d) for d in runner.preferred_running_days
            )

            return (
                f"Anotei que você curte o longão {day_label}! 🙌 Mas "
                f"{day_label} não está nos seus dias de treino ({current}). "
                f"Quer que eu inclua {day_label} nos seus dias? É só falar."
            )

        RunnerProfileRepository().update_fields(
            profile,
            {"preferred_long_run_day": day},
        )

        # atleta com treinador: só registra, não gera plano
        if runner.external_coach:

            return (
                f"Fechou! Anotei que você faz o longão {day_label}. 💪"
            )

        # regera o plano da semana já com o longão no dia pedido
        _, plan = await CurrentPlanProvider.for_profile(
            profile,
            force=True,
        )

        has_long = any(
            session.workout_type == "LONG_RUN"
            for session in plan.sessions
        )

        # Iniciante ainda não tem longão (o coach decide pela evolução):
        # guarda a preferência pra quando o longão entrar no plano.
        if not has_long:

            return (
                f"Anotei que você curte o longão {day_label}! 🙌 Por "
                f"enquanto seu foco é construir base — quando o longão "
                f"entrar no seu plano, vai ser {day_label}. Bora seguir. 💪"
            )

        plan_text = WeeklyPlanMessageFormatter.week_plan_message(
            runner.name,
            plan,
        )

        return (
            f"Fechou, {runner.name}! Ajustei seu plano pra fazer o longão "
            f"{day_label}. 💪\n\n{plan_text}"
        )
