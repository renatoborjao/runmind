from app.core.weekdays import weekday_label
from app.domain.entities.training_plan import TrainingPlan


class WeeklyPlanMessageFormatter:

    @staticmethod
    def format(
        runner_name: str,
        plan: TrainingPlan,
    ) -> str:

        lines = [
            "🏃 RunMind — Plano da semana",
            "",
            f"Bom domingo, {runner_name}! Aqui está seu plano "
            f"pra semana de {plan.week_start.strftime('%d/%m')}:",
            "",
        ]

        lines.extend(
            WeeklyPlanMessageFormatter.session_lines(plan)
        )

        lines.append("")

        lines.append("Bora treinar! 💪")

        return "\n".join(lines)

    @staticmethod
    def session_lines(
        plan: TrainingPlan,
    ) -> list[str]:
        """Só as linhas de sessão, em ordem cronológica — para usar em
        mensagens que não são a de domingo."""

        sessions = sorted(
            plan.sessions,
            key=lambda session: plan.session_date(session),
        )

        return [
            WeeklyPlanMessageFormatter._session_line(plan, session)
            for session in sessions
        ]

    @staticmethod
    def _session_line(
        plan: TrainingPlan,
        session,
    ) -> str:

        session_date = plan.session_date(session).strftime("%d/%m")

        pace = ""

        if session.target_pace_min and session.target_pace_max:

            pace = (
                f" — pace {session.target_pace_min}-"
                f"{session.target_pace_max} min/km"
            )

        return (
            f"• {weekday_label(session.day)} ({session_date}): "
            f"{session.workout_type} "
            f"— {session.planned_distance_km or 0:.1f} km{pace}"
        )
