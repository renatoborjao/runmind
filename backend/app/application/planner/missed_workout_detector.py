from datetime import date, timedelta

from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.core.weekdays import WEEKDAYS
from app.domain.entities.activity import Activity
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan

_RUNNING_KINDS = {"run", "walk", "run_walk"}


class MissedWorkoutDetector:
    """Havia treino de corrida planejado ONTEM que não foi cumprido? O plano
    é guia, não obrigação — mas o coach nota o furo pra puxar conversa."""

    @staticmethod
    def yesterday_missed(
        plan: TrainingPlan,
        activities: list[Activity],
        reference_date: date,
    ) -> PlannedSession | None:

        yesterday = reference_date - timedelta(days=1)

        # só olha ontem se cai na semana DESTE plano (evita cobrar um dia
        # que pertencia ao plano da semana passada, ex.: segunda olhando
        # o domingo anterior)
        week_end = plan.week_start + timedelta(days=6)

        if not (plan.week_start <= yesterday <= week_end):

            return None

        weekday = WEEKDAYS[yesterday.weekday()]

        session = plan.find_session_by_day(weekday)

        # dia de descanso ou sessão que não é corrida/caminhada: nada a cobrar
        if session is None or session.kind not in _RUNNING_KINDS:

            return None

        fulfilled = WeeklyPlanMatcher.fulfilled_days(plan, activities)

        # houve treino real casado com a sessão de ontem: cumpriu, sem furo
        if session.day in fulfilled:

            return None

        return session
