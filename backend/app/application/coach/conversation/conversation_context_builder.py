from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)
from app.application.history.metrics_resolver import (
    MetricsResolver,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.application.planner.weekly_plan_service import (
    WeeklyPlanService,
)
from app.application.use_cases.load_runner_profile import (
    LoadRunnerProfile,
)
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import today_local
from app.core.weekdays import weekday_label
from app.domain.entities.training_goal import (
    TrainingGoal,
)


class ConversationContextBuilder:

    @staticmethod
    async def build(
        profile: str,
    ) -> str:

        runner = LoadRunnerProfile.execute(profile)

        history = await LoadTrainingHistory.execute(
            profile=profile,
        )

        assessment = TrainingAssessmentBuilder.build(
            runner,
            history,
        )

        metrics = MetricsResolver.resolve(
            runner,
            history,
        )

        goal = TrainingGoal(
            name=runner.goal,
            distance_km=10,
            target_time=runner.target_time,
            race_date=None,
        )

        plan = WeeklyPlanService.get_or_generate(
            profile=profile,
            runner=runner,
            assessment=assessment,
            metrics=metrics,
            goal=goal,
        )

        facts = (
            f"Corredor: {runner.name}\n"
            f"Meta: {runner.goal}\n"
            f"Volume semanal atual: {assessment.current_weekly_volume:.1f} km "
            f"(meta recomendada: {assessment.recommended_weekly_volume:.1f} km)\n"
            f"Consistência: {assessment.consistency:.0f}%\n"
            f"Último treino: {ConversationContextBuilder._last_activity_summary(history)}\n"
            f"Próximo treino planejado: {ConversationContextBuilder._next_session_summary(plan)}\n"
        )

        week_plan = ConversationContextBuilder._week_plan_summary(plan)

        if week_plan:

            facts = f"{facts}\n{week_plan}\n"

        memory = RunnerMemoryService.render(profile)

        if memory:

            facts = f"{facts}\n{memory}\n"

        return facts

    @staticmethod
    def _week_plan_summary(
        plan,
    ) -> str:
        """Plano completo da semana — permite ao coach responder
        "qual meu treino de sábado?" sem inventar."""

        if not plan.sessions:

            return ""

        lines = ["Plano da semana completo:"]

        lines.extend(
            WeeklyPlanMessageFormatter.session_lines(plan)
        )

        if plan.source == "externo":

            lines.append(
                "(plano montado pelo treinador do corredor — o "
                "RunMind só acompanha)"
            )

        return "\n".join(lines)

    @staticmethod
    def _last_activity_summary(
        history,
    ) -> str:

        latest = history.latest

        if latest is None:

            return "nenhum treino recente encontrado"

        distance_km = latest.distance / 1000

        return f"{latest.name}, {distance_km:.1f} km"

    @staticmethod
    def _next_session_summary(
        plan,
        reference_date=None,
    ) -> str:

        if not plan.sessions:

            return "nenhum treino planejado ainda"

        today = reference_date or today_local()

        upcoming = sorted(
            plan.sessions,
            key=lambda session: plan.session_date(session),
        )

        session = next(
            (
                s
                for s in upcoming
                if plan.session_date(s) >= today
            ),
            upcoming[0],
        )

        session_date = plan.session_date(session)

        pace = ""

        if session.target_pace_min and session.target_pace_max:

            pace = f" — pace {session.target_pace_min}-{session.target_pace_max} min/km"

        adjustment = ""

        if session.adjusted and session.adjustment_reason:

            adjustment = f" [AJUSTADO: {session.adjustment_reason}]"

        return (
            f"{weekday_label(session.day)} "
            f"({session_date.strftime('%d/%m')}) — "
            f"{session.workout_type} "
            f"({session.planned_distance_km or 0:.1f} km) — "
            f"{session.objective}{pace}{adjustment}"
        )
