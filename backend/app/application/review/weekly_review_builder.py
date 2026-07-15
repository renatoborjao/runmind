from __future__ import annotations

from datetime import date

from app.application.history.consistency_calculator import (
    ConsistencyCalculator,
)
from app.application.history.evolution_analyzer import EvolutionAnalyzer
from app.application.history.week_comparator import WeekComparator
from app.application.history.weekly_buckets import activity_date
from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.core.clock import today_local
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)

TREND_WEEKS = 8

_RUNNING_KINDS = {"run", "walk", "run_walk"}


class WeeklyReviewBuilder:
    """Monta os dados do resumo semanal (semana que está fechando) — números,
    tendência, consistência, ADERÊNCIA ao plano, longão da semana e a META do
    atleta (pra a mensagem falar a língua do objetivo: prova ou saúde)."""

    @staticmethod
    def build(
        runner: RunnerProfile,
        history: TrainingHistory,
        reference_date: date | None = None,
    ) -> dict:

        reference_date = reference_date or today_local()

        comparison = WeekComparator.compare(
            history,
            reference_date=reference_date,
        )

        evolution = EvolutionAnalyzer.analyze(
            history,
            weeks=TREND_WEEKS,
            reference_date=reference_date,
        )

        consistency = ConsistencyCalculator.calculate(
            history,
            runner.weekly_training_days,
            reference_date=reference_date,
        )

        review_week = date.fromisoformat(
            comparison["current_week"]["week_start"]
        )

        return {
            "week_start": comparison["current_week"]["week_start"],
            "comparison": comparison,
            "trends": evolution["trends"],
            "consistency": consistency,
            "goal": WeeklyReviewBuilder._goal_data(runner, reference_date),
            "adherence": WeeklyReviewBuilder._adherence(
                runner.id,
                history,
                review_week,
            ),
            "longest_km": WeeklyReviewBuilder._longest_km(
                history,
                review_week,
            ),
        }

    @staticmethod
    def _goal_data(
        runner: RunnerProfile,
        reference_date: date,
    ) -> dict:
        """Objetivo do atleta, pra a mensagem se adaptar: prova/marca com data
        futura vira contagem regressiva; sem prova (saúde/evolução) fica só o
        texto do objetivo — sem cobrança de pace de prova."""

        goal = BuildTrainingGoal.execute(runner)

        has_race = (
            goal.race_date is not None and goal.race_date > reference_date
        )

        weeks_to_race = (
            (goal.race_date - reference_date).days // 7 if has_race else None
        )

        return {
            "name": goal.name,
            "target_time": goal.target_time,
            "race_date": goal.race_date.isoformat() if goal.race_date else None,
            "weeks_to_race": weeks_to_race,
            "has_race": has_race,
        }

    @staticmethod
    def _adherence(
        profile: str,
        history: TrainingHistory,
        review_week: date,
    ) -> dict | None:
        """Quantos treinos do plano da semana que fechou foram cumpridos.
        None se não achar o plano dessa semana (ex.: atleta sem plano)."""

        plan = WeeklyReviewBuilder._plan_for_week(profile, review_week)

        if plan is None or not plan.sessions:

            return None

        running = [s for s in plan.sessions if s.kind in _RUNNING_KINDS]

        if not running:

            return None

        fulfilled = WeeklyPlanMatcher.fulfilled_days(
            plan,
            history.activities,
        )

        done = len([s for s in running if s.day in fulfilled])

        return {"planned": len(running), "done": done}

    @staticmethod
    def _plan_for_week(profile: str, week: date):
        """O plano cuja semana bate com a que fechou. No domingo 20h o plano
        da PRÓXIMA já foi entregue (15h), então o da semana que fecha está no
        histórico — procura lá primeiro, depois no atual."""

        repo = WeeklyPlanRepository()

        for plan in repo.history(profile):

            if plan.week_start == week:

                return plan

        current = repo.load(profile)

        if current is not None and current.week_start == week:

            return current

        return None

    @staticmethod
    def _longest_km(
        history: TrainingHistory,
        review_week: date,
    ) -> float | None:
        """Maior treino (km) da semana que fechou."""

        week_key = review_week.isocalendar()[:2]

        distances = [
            activity.distance / 1000
            for activity in history.activities
            if activity_date(activity).isocalendar()[:2] == week_key
            and activity.distance
        ]

        return round(max(distances), 1) if distances else None
