from datetime import timedelta

from app.application.planner.pace_formatter import PaceFormatter
from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.core.weekdays import weekday_label, weekday_name
from app.domain.entities.activity import Activity
from app.domain.entities.training_plan import TrainingPlan


class ExecutedWeekSummary:
    """Resumo do que o atleta REALMENTE fez na semana do último plano —
    distância e pace de cada treino, casado com o que estava planejado, e
    o que não foi feito. É o 'vivo' que a IA consulta pra ajustar a
    próxima semana (bateu os paces? completou? faltou?)."""

    @staticmethod
    def build(
        last_plan: TrainingPlan | None,
        activities: list[Activity],
    ) -> str:

        if last_plan is None or not last_plan.sessions:

            return ""

        week_start = last_plan.week_start

        week_end = week_start + timedelta(days=6)

        week_activities = sorted(
            (
                activity
                for activity in activities
                if week_start <= activity.start_date.date() <= week_end
            ),
            key=lambda activity: activity.start_date,
        )

        lines = []

        done_days = set()

        for activity in week_activities:

            session = WeeklyPlanMatcher.match(
                last_plan,
                week_activities,
                activity,
            )

            if session is not None:

                done_days.add(session.day)

            lines.append(
                ExecutedWeekSummary._activity_line(activity, session)
            )

        # sessões planejadas que NÃO foram feitas
        for session in last_plan.sessions:

            if session.day not in done_days:

                lines.append(
                    f"- {weekday_label(session.day)} "
                    f"({session.workout_type}): não realizado"
                )

        if not lines:

            return ""

        return "Treinos realizados na semana do último plano:\n" + "\n".join(
            lines
        )

    @staticmethod
    def _activity_line(activity: Activity, session) -> str:

        distance_km = activity.distance / 1000

        pace = ExecutedWeekSummary._pace(activity)

        planned = (
            f" (planejado: {session.workout_type})"
            if session is not None
            else " (treino extra)"
        )

        day = weekday_label(weekday_name(activity.start_date))

        return f"- {day}: {distance_km:.1f} km a {pace}/km{planned}"

    @staticmethod
    def _pace(activity: Activity) -> str:

        if activity.average_speed and activity.average_speed > 0:

            return PaceFormatter.format((1000 / activity.average_speed) / 60)

        return "?"
