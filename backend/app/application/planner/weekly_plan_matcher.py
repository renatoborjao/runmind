from datetime import timedelta

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

            executed_km = activity.distance / 1000

            best = min(
                remaining,
                key=lambda session: abs(
                    (session.planned_distance_km or 0) - executed_km
                ),
            )

            remaining.remove(best)

            assignments[activity.id] = best

        return assignments
