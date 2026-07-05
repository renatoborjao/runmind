from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)
from app.application.history.metrics_resolver import (
    MetricsResolver,
)
from app.application.planner.weekly_plan_matcher import (
    WeeklyPlanMatcher,
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
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.conversation_repository import (
    ConversationRepository,
)
from app.application.use_cases.build_training_goal import (
    BuildTrainingGoal,
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

        goal = BuildTrainingGoal.execute(runner)

        plan = WeeklyPlanService.get_or_generate(
            profile=profile,
            runner=runner,
            assessment=assessment,
            metrics=metrics,
            goal=goal,
            history=history,
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

        race_line = ConversationContextBuilder._race_summary(goal)

        if race_line:

            facts = f"{facts}{race_line}\n"

        week_plan = ConversationContextBuilder._week_plan_summary(
            plan,
            history,
        )

        if week_plan:

            facts = f"{facts}\n{week_plan}\n"

        lifetime = ConversationContextBuilder._lifetime_summary(
            profile,
        )

        if lifetime:

            facts = f"{facts}{lifetime}\n"

        memory = RunnerMemoryService.render(profile)

        if memory:

            facts = f"{facts}\n{memory}\n"

        summary = ConversationRepository().load_summary(
            profile,
        )["summary"]

        if summary:

            facts = (
                f"{facts}\nResumo de conversas anteriores: "
                f"{summary}\n"
            )

        return facts

    @staticmethod
    def _race_summary(
        goal,
        reference_date=None,
    ) -> str:
        """Prova alvo, quando existir e for futura — atleta sem prova
        não tem essa linha (nada é inventado)."""

        if goal.race_date is None:

            return ""

        today = reference_date or today_local()

        if goal.race_date <= today:

            return ""

        weeks = (goal.race_date - today).days // 7

        target = (
            f", alvo {goal.target_time}" if goal.target_time else ""
        )

        return (
            f"Prova alvo: {goal.name} em "
            f"{goal.race_date.strftime('%d/%m/%Y')} "
            f"(daqui a {weeks} semanas{target})\n"
        )

    @staticmethod
    def _lifetime_summary(
        profile: str,
    ) -> str:
        """Agregados do arquivo permanente — o coach responde sobre o
        histórico de vida, além da janela recente do Strava."""

        stats = ActivityArchiveRepository().stats(profile)

        if stats is None:

            return ""

        first = stats["first_date"]

        first_label = f"{first[5:7]}/{first[:4]}"  # mm/aaaa

        return (
            f"Histórico geral registrado: {stats['total_runs']} "
            f"treinos, {stats['total_km']:.0f} km desde "
            f"{first_label}; maior treino: "
            f"{stats['longest_km']:.1f} km\n"
        )

    @staticmethod
    def _week_plan_summary(
        plan,
        history,
    ) -> str:
        """Plano completo da semana — permite ao coach responder
        "qual meu treino de sábado?" sem inventar. Marca feito x não feito
        validando o histórico real (não assume que passou = feito)."""

        if not plan.sessions:

            return ""

        done_days = WeeklyPlanMatcher.fulfilled_days(
            plan,
            history.activities,
        )

        lines = ["Plano da semana completo:"]

        lines.extend(
            WeeklyPlanMessageFormatter.session_lines(
                plan,
                today_local(),
                done_days=done_days,
            )
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
