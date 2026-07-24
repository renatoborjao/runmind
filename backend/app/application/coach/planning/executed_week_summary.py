from datetime import date, timedelta

from app.application.planner.pace_formatter import PaceFormatter
from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.core.weekdays import WEEKDAYS, weekday_label, weekday_name
from app.domain.entities.activity import Activity
from app.domain.entities.training_plan import TrainingPlan

# nome interno do dia ("Sunday") -> índice ISO (0=segunda ... 6=domingo)
_DAY_INDEX = {name: idx for idx, name in WEEKDAYS.items()}


class ExecutedWeekSummary:
    """Resumo do que o atleta REALMENTE fez na semana do último plano —
    distância e pace de cada treino, casado com o que estava planejado, e
    o que não foi feito. É o 'vivo' que a IA consulta pra ajustar a
    próxima semana (bateu os paces? completou? faltou?)."""

    @staticmethod
    def build(
        last_plan: TrainingPlan | None,
        activities: list[Activity],
        reference_date: date | None = None,
    ) -> str:
        """`reference_date` (hoje, no fuso do atleta): uma sessão cujo DIA
        ainda não chegou NÃO é 'não realizado' — ela simplesmente ainda não
        venceu. Sem isso, ler o plano numa sexta mostrava o longão de domingo
        como furado (mesma guarda que o AdherenceAnalyzer já tem)."""

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

        # sessões planejadas que NÃO foram feitas — mas só as que JÁ venceram
        # (uma sessão futura não é furo, só ainda não chegou)
        for session in last_plan.sessions:

            if session.day in done_days:

                continue

            if ExecutedWeekSummary._is_future(
                session.day, week_start, reference_date,
            ):

                continue

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
    def _is_future(
        day: str,
        week_start: date,
        reference_date: date | None,
    ) -> bool:
        """A sessão cai depois de hoje? Sem reference_date, mantém o
        comportamento antigo (nada é considerado futuro)."""

        if reference_date is None:

            return False

        offset = _DAY_INDEX.get(day)

        if offset is None:

            return False

        return week_start + timedelta(days=offset) > reference_date

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
