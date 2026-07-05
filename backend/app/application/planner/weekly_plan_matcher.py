from datetime import timedelta

from app.core.weekdays import weekday_name
from app.domain.entities.activity import Activity
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan


class WeeklyPlanMatcher:
    """Casa um treino executado com a sessão que ele cumpriu no plano.

    O plano é um guia, não uma obrigação de DIA: o corredor pode fazer a
    rodagem na segunda em vez de terça. Então, em vez de casar por dia da
    semana, casamos por DISTÂNCIA — cada corrida da semana credita a
    sessão planejada de distância mais próxima ainda não cumprida. O que
    exceder o número de sessões (ou cair fora da semana do plano) é treino
    extra (None).
    """

    @staticmethod
    def match(
        plan: TrainingPlan,
        activities: list[Activity],
        current: Activity,
    ) -> PlannedSession | None:

        if not plan.sessions:

            return None

        assignments = WeeklyPlanMatcher._assign_week(
            plan,
            activities,
        )

        return assignments.get(current.id)

    @staticmethod
    def fulfilled_days(
        plan: TrainingPlan,
        activities: list[Activity],
    ) -> set[str]:
        """Dias (da semana) das sessões que FORAM cumpridas — houve um
        treino real casado com elas. Usado para o plano marcar feito x não
        feito, validando contra o histórico do Strava."""

        if not plan.sessions:

            return set()

        assignments = WeeklyPlanMatcher._assign_week(plan, activities)

        return {
            session.day
            for session in assignments.values()
            if session is not None
        }

    @staticmethod
    def _assign_week(
        plan: TrainingPlan,
        activities: list[Activity],
    ) -> dict[int, PlannedSession | None]:
        """Atribuição gulosa e cronológica: percorre as corridas da semana
        da mais antiga para a mais nova; cada uma pega a sessão restante de
        distância mais próxima. Determinístico e previsível ('conforme vai
        treinando')."""

        week_start = plan.week_start

        week_end = week_start + timedelta(days=6)

        week_activities = sorted(
            (
                activity
                for activity in activities
                if week_start <= activity.start_date.date() <= week_end
            ),
            key=lambda activity: activity.start_date,
        )

        remaining = list(plan.sessions)

        assignments: dict[int, PlannedSession | None] = {}

        for activity in week_activities:

            if not remaining:

                assignments[activity.id] = None

                continue

            chosen = WeeklyPlanMatcher._match_one(activity, remaining)

            remaining.remove(chosen)

            assignments[activity.id] = chosen

        return assignments

    @staticmethod
    def _match_one(
        activity: Activity,
        remaining: list[PlannedSession],
    ) -> PlannedSession:
        """Prioriza o DIA: treinou num dia que tem sessão planejada ->
        casa com a sessão daquele dia (o atleta cumpriu o dia). Só quando
        treinou num dia SEM sessão (fora do plano) cai na distância mais
        próxima."""

        activity_day = weekday_name(activity.start_date)

        same_day = next(
            (
                session
                for session in remaining
                if session.day.lower() == activity_day.lower()
            ),
            None,
        )

        if same_day is not None:

            return same_day

        executed_km = activity.distance / 1000

        return min(
            remaining,
            key=lambda session: abs(
                (session.planned_distance_km or 0) - executed_km
            ),
        )
