from __future__ import annotations

from datetime import date, timedelta

from app.application.history.adherence_analyzer import AdherenceAnalyzer
from app.application.history.consistency_calculator import (
    ConsistencyCalculator,
)
from app.application.history.evolution_analyzer import EvolutionAnalyzer
from app.application.history.race_time_predictor import RaceTimePredictor
from app.application.history.week_comparator import WeekComparator
from app.application.history.weekly_buckets import (
    activity_date,
    group_by_week,
    last_week_keys,
    week_stats,
)
from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.core.clock import today_local
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from app.domain.value_objects.sports import is_run_sport
from app.infrastructure.persistence.race_result_repository import (
    RaceResultRepository,
)
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)

TREND_WEEKS = 8

_RUNNING_KINDS = {"run", "walk", "run_walk"}

# a semana anterior abaixo desta fração da média das 4 antes dela é RECESSO (pausa, viagem, gripe)
_BREAK_FRACTION = 0.4


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
            "goal": WeeklyReviewBuilder._goal_data(
                runner, history, reference_date,
            ),
            "adherence": WeeklyReviewBuilder._adherence(
                runner.id,
                history,
                review_week,
            ),
            "adherence_history": AdherenceAnalyzer.analyze(
                WeeklyReviewBuilder._all_plans(runner.id),
                history,
                until_week=review_week,
            ),
            "longest_km": WeeklyReviewBuilder._longest_km(
                history,
                review_week,
            ),
            # a semana anterior foi de RECESSO? ("+773%" contra uma semana parada não é carga)
            "previous_week_break": WeeklyReviewBuilder._previous_was_break(
                history, review_week,
            ),
            # as corridas de ESTEIRA da semana (pace/distância estimados) e se o atleta tem FC
            # medida nela — a leitura da semana não pode provar ritmo com a esteira nem citar FC
            # de quem corre sem monitor
            "indoor_runs": WeeklyReviewBuilder._indoor_runs(history, review_week),
            "has_hr": WeeklyReviewBuilder._week_has_hr(history, review_week),
            # a PROVA que aconteceu nesta semana (se houve) — o destaque do
            # resumo. Vem do resultado persistido (o race_date já foi consumido
            # pelo debrief). None quando não houve prova na semana.
            "race": WeeklyReviewBuilder._race_in_week(runner.id, review_week),
            # o plano da próxima semana sai logo depois do resumo (mesmo dia) —
            # só pra quem tem plano NOSSO (treinador externo conduz o dele).
            "plan_incoming": not runner.external_coach,
        }

    @staticmethod
    def _goal_data(
        runner: RunnerProfile,
        history: TrainingHistory,
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

        # previsão de tempo de prova só faz sentido pra quem TEM prova de
        # verdade (data marcada) — não pra quem só tem uma distância de
        # treino sem competição nenhuma no horizonte
        predicted_time = (
            RaceTimePredictor.predict_formatted(
                history, goal.distance_km, goal.target_time, profile=runner.id,
            )
            if has_race
            else None
        )

        return {
            "name": goal.name,
            # rótulo da PROVA (distância), separado do objetivo de fundo (name)
            # — senão a narrativa diz "faltam 2 semanas pro seu 21km" quando a
            # prova é um 10k (bug do Renato).
            "race_label": goal.race_label,
            "target_time": goal.target_time,
            "race_date": goal.race_date.isoformat() if goal.race_date else None,
            "weeks_to_race": weeks_to_race,
            "has_race": has_race,
            "predicted_time": predicted_time,
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
    def _all_plans(profile: str) -> list[TrainingPlan]:
        """Todos os planos que o atleta já recebeu: o histórico mais o
        vigente (que ainda não foi arquivado). Quem consome deduplica."""

        repo = WeeklyPlanRepository()

        plans = list(repo.history(profile))

        current = repo.load(profile)

        if current is not None:

            plans.append(current)

        return plans

    @staticmethod
    def _plan_for_week(profile: str, week: date):
        """O plano cuja semana bate com a que fechou. No domingo 20h o plano
        da PRÓXIMA já foi entregue (15h), então o da semana que fecha está no
        histórico — procura lá primeiro, depois no atual."""

        for plan in WeeklyReviewBuilder._all_plans(profile):

            if plan.week_start == week:

                return plan

        return None

    @staticmethod
    def _race_in_week(profile: str, review_week: date) -> dict | None:
        """O resultado da prova cuja data cai na semana que fechou (por semana
        ISO). None se não houve prova. Best-effort — nunca derruba o resumo."""

        try:

            week_key = review_week.isocalendar()[:2]

            for result in RaceResultRepository().load(profile):

                raw = result.get("date")

                if not raw:

                    continue

                if date.fromisoformat(raw).isocalendar()[:2] == week_key:

                    return result

        except Exception as e:

            print(f"Detecção de prova na semana falhou p/ '{profile}': {e}")

        return None

    @staticmethod
    def _previous_was_break(history: TrainingHistory, review_week: date) -> bool:
        """A semana anterior à que fechou ficou muito abaixo do normal DELE (menos de 40% da
        média das 4 semanas antes dela, que precisam ter corrida em pelo menos 2)? Então a conta
        "esta vs anterior" mede a volta de uma pausa, não um salto de carga."""

        buckets = group_by_week(history.activities)

        previous_key = (review_week - timedelta(weeks=1)).isocalendar()[:2]

        before = [
            week_stats(buckets.get(key, []))["distance_km"]
            for key in last_week_keys(review_week - timedelta(weeks=2), 4)
        ]

        ran = [km for km in before if km > 0]

        if len(ran) < 2:

            return False

        typical = sum(ran) / len(ran)

        previous_km = week_stats(buckets.get(previous_key, []))["distance_km"]

        return previous_km < typical * _BREAK_FRACTION

    @staticmethod
    def _week_runs(history: TrainingHistory, review_week: date) -> list:

        week_key = review_week.isocalendar()[:2]

        return [
            activity
            for activity in history.activities
            if activity_date(activity).isocalendar()[:2] == week_key
            and is_run_sport(activity.sport)
        ]

    @staticmethod
    def _indoor_runs(history: TrainingHistory, review_week: date) -> list[dict]:

        return [
            {
                "day": activity_date(activity).strftime("%d/%m"),
                "km": round(activity.distance / 1000, 1),
            }
            for activity in WeeklyReviewBuilder._week_runs(history, review_week)
            if activity.raw.get("trainer")
        ]

    @staticmethod
    def _week_has_hr(history: TrainingHistory, review_week: date) -> bool:
        """Alguma corrida da semana tem FC medida? Sem nenhuma (corre sem monitor), a leitura
        não pode falar de frequência cardíaca. Semana sem corrida: não restringe."""

        runs = WeeklyReviewBuilder._week_runs(history, review_week)

        return not runs or any(run.average_heartrate for run in runs)

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
