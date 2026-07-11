from datetime import date, timedelta

from app.application.coach.planning.missed_workout_judge import (
    MissedWorkoutJudge,
)
from app.application.history.metrics_resolver import MetricsResolver
from app.application.history.runner_baseline_builder import (
    RunnerBaselineBuilder,
)
from app.application.planner.current_plan_provider import CurrentPlanProvider
from app.application.planner.missed_workout_detector import (
    MissedWorkoutDetector,
)
from app.application.planner.pace_formatter import PaceFormatter
from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import now_local, today_local
from app.domain.entities.plan_proposal import PlanProposal
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory
from app.infrastructure.persistence.missed_notification_repository import (
    MissedNotificationRepository,
)
from app.infrastructure.persistence.plan_proposal_repository import (
    PlanProposalRepository,
)

_RUNNING_KINDS = {"run", "walk", "run_walk"}


class MissedWorkoutFlow:
    """Furou o treino de ontem? A IA-treinadora decide, com base no retrato
    real (histórico/evolução), se o plano segue igual (só tranquiliza) ou se
    vale reorganizar os próximos dias — e aí guarda a proposta pro 'sim'.
    Nunca aplica nada sozinho."""

    @staticmethod
    async def process(
        profile: str,
        reference_date: date | None = None,
    ) -> tuple[RunnerProfile, str] | None:
        """Devolve (runner, mensagem) a enviar, ou None se não houve furo,
        já avisamos, ou é atleta de treinador externo."""

        reference_date = reference_date or today_local()

        runner = LoadRunnerProfile.execute(profile)

        # treinador humano: RunMind não reprograma o plano dele
        if runner.external_coach:

            return None

        history = await LoadTrainingHistory.execute(profile=profile)

        _, plan = await CurrentPlanProvider.for_profile(profile)

        missed = MissedWorkoutDetector.yesterday_missed(
            plan,
            history.activities,
            reference_date,
        )

        if missed is None:

            return None

        missed_date = (reference_date - timedelta(days=1)).isoformat()

        marker = MissedNotificationRepository()

        # já avisamos esse mesmo furo: não repete
        if marker.last_notified(profile) == missed_date:

            return None

        running = [s for s in plan.sessions if s.kind in _RUNNING_KINDS]

        fulfilled = WeeklyPlanMatcher.fulfilled_days(plan, history.activities)

        done = len([s for s in running if s.day in fulfilled])

        judgment = await MissedWorkoutJudge.judge(
            runner=runner,
            plan=plan,
            missed=missed,
            done=done,
            total=len(running),
            portrait=MissedWorkoutFlow._portrait(runner, history),
        )

        if judgment is None:

            return None

        # re-plano necessário: guarda a proposta pro atleta confirmar.
        # sem operações = só informa (plano segue igual), nada a propor.
        if judgment.operations:

            PlanProposalRepository().save(
                profile,
                PlanProposal(
                    kind="missed",
                    week_start=plan.week_start.isoformat(),
                    preview=judgment.message,
                    created_at=now_local().isoformat(),
                    operations=judgment.operations,
                ),
            )

        marker.mark(profile, missed_date)

        return runner, judgment.message

    @staticmethod
    def _portrait(
        runner: RunnerProfile,
        history: TrainingHistory,
    ) -> str:
        """Retrato compacto do atleta pra IA decidir com base real — volume,
        tendência e paces. Sem histórico utilizável, volta vazio (o juiz
        lida)."""

        try:

            baseline = RunnerBaselineBuilder.build(history, runner)

            metrics = MetricsResolver.resolve(runner, history)

            return (
                "Volume ~%.0f km/sem (última %.0f, melhor %.0f), tendência %s. "
                "Rodagem típica ~%.0f km; maior treino ~%.0f km. "
                "Paces (min/km): fácil %s-%s, limiar %s, VO2 %s."
                % (
                    baseline.weekly_km, baseline.last_week_km,
                    baseline.max_week_km, baseline.trend,
                    baseline.typical_run_km, baseline.longest_km,
                    PaceFormatter.format(metrics.easy_pace_min),
                    PaceFormatter.format(metrics.easy_pace_max),
                    PaceFormatter.format(metrics.threshold_pace),
                    PaceFormatter.format(metrics.vo2_pace),
                )
            )

        except Exception as e:

            print(f"Retrato do furou-ontem falhou para '{runner.name}': {e}")

            return ""
