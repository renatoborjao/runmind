from datetime import timedelta

from app.core.weekdays import weekday_name
from app.domain.entities.activity import Activity
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan


class WeeklyPlanMatcher:
    """Casa um treino executado com a sessão que ele cumpriu no plano.

    O plano é um guia, não uma obrigação de DIA, mas o DIA manda quando
    bate: casamos em dois passos.

    1. Por DIA: quem treinou num dia que tem sessão planejada cumpre a
       sessão daquele dia (se houver mais de uma corrida no dia, a de
       distância mais próxima fica com a sessão).
    2. Por DISTÂNCIA: as corridas em dias SEM sessão casam com a sessão
       restante de distância mais próxima — desde que dentro de uma
       tolerância; longe demais é treino extra (None), não credita.

    Fazer o passo do dia ANTES do da distância evita que uma corrida fora
    do plano (ex.: segunda) roube a sessão de um dia planejado (ex.: o
    longão de sábado) só por ter distância parecida.
    """

    # Tolerância do casamento por distância (passo 2): credita a sessão só
    # se a diferença ficar dentro de 2 km OU 30% da distância planejada.
    TOLERANCE_KM = 2.0
    TOLERANCE_FRACTION = 0.30

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
        """Dois passos: primeiro casa por DIA (corrida num dia planejado
        cumpre aquela sessão), depois casa o resto por DISTÂNCIA dentro de
        uma tolerância. Determinístico e previsível."""

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

        # Passo 1 — por DIA: cada sessão fica com a corrida do mesmo dia da
        # semana (a de distância mais próxima, se houver mais de uma).
        for session in plan.sessions:

            same_day = [
                activity
                for activity in week_activities
                if activity.id not in assignments
                and weekday_name(activity.start_date).lower()
                == session.day.lower()
            ]

            if not same_day:

                continue

            chosen = min(
                same_day,
                key=lambda activity: abs(
                    (session.planned_distance_km or 0)
                    - activity.distance / 1000
                ),
            )

            assignments[chosen.id] = session

            remaining.remove(session)

        # Passo 2 — por DISTÂNCIA: corridas em dias sem sessão casam com a
        # sessão restante mais próxima, dentro da tolerância; senão, extra.
        for activity in week_activities:

            if activity.id in assignments:

                continue

            chosen = WeeklyPlanMatcher._closest_within_tolerance(
                activity,
                remaining,
            )

            assignments[activity.id] = chosen

            if chosen is not None:

                remaining.remove(chosen)

        return assignments

    @staticmethod
    def _closest_within_tolerance(
        activity: Activity,
        remaining: list[PlannedSession],
    ) -> PlannedSession | None:
        """Sessão restante de distância mais próxima da corrida, desde que
        dentro da tolerância; nenhuma perto o bastante -> None (extra)."""

        executed_km = activity.distance / 1000

        def within(session: PlannedSession) -> bool:

            planned = session.planned_distance_km or 0

            limit = max(
                WeeklyPlanMatcher.TOLERANCE_KM,
                WeeklyPlanMatcher.TOLERANCE_FRACTION * planned,
            )

            return abs(planned - executed_km) <= limit

        candidates = [
            session for session in remaining if within(session)
        ]

        if not candidates:

            return None

        return min(
            candidates,
            key=lambda session: abs(
                (session.planned_distance_km or 0) - executed_km
            ),
        )
