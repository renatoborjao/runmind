from datetime import date

from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)
from app.application.coach.planning.coach_plan_engine import CoachPlanEngine
from app.application.coach.planning.executed_week_summary import (
    ExecutedWeekSummary,
)
from app.application.coach.planning.plan_context_builder import (
    PlanContextBuilder,
)
from app.application.history.runner_baseline_builder import (
    RunnerBaselineBuilder,
)
from app.application.planner.engines.phase_engine import PhaseEngine
from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.core.clock import today_local
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_assessment import TrainingAssessment
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


class AIPlanService:
    """Gera o plano da semana pela IA-treinadora a partir do retrato real
    do atleta. Cache por semana; treinador externo e run/walk seguem o
    caminho determinístico; se a IA falhar, cai no determinístico."""

    @staticmethod
    async def ensure_plan(
        profile: str,
        runner: RunnerProfile,
        assessment: TrainingAssessment,
        metrics: RunnerMetrics,
        goal: TrainingGoal,
        history: TrainingHistory,
        reference_date: date | None = None,
        force: bool = False,
    ) -> TrainingPlan:

        reference_date = reference_date or today_local()

        week_start = WeeklyPlanService.active_week_start(reference_date)

        repository = WeeklyPlanRepository()

        existing = repository.load(profile)

        # já há plano desta semana ATIVA (ou de uma futura já entregue):
        # reaproveita. force=True (o atleta pediu uma mudança) regenera pela
        # IA — mantendo o plano RICO, nunca caindo pro determinístico como
        # plano principal. O `>=` evita que uma leitura de domingo à tarde
        # regenere a semana atual por cima do plano da próxima já entregue.
        if (
            not force
            and existing is not None
            and existing.week_start >= week_start
        ):

            return existing

        # só treinador externo fica fora da IA (RunMind só acompanha o
        # plano dele). Iniciante run/walk TAMBÉM é gerado pela IA, com os
        # dados do onboarding (peso/altura/capacidade) no contexto.
        if runner.external_coach:

            return AIPlanService._deterministic(
                profile, runner, assessment, metrics, goal,
                history, reference_date,
            )

        try:

            context = AIPlanService._build_context(
                profile, runner, metrics, goal, history,
                repository, week_start, assessment.run_walk,
            )

            plan = await CoachPlanEngine.generate(
                runner_name=runner.name,
                objective=goal.name,
                week_start=week_start,
                context=context,
            )

            # Fase real do ciclo (ancorada na prova): a IA não sabe "que
            # semana do macrociclo é esta", então marca "IA" ao montar; aqui
            # gravamos a fase calculada (BASE/BUILD/PICO/TAPER) pra a mensagem
            # do plano mostrar "📈 Fase" igual ao caminho determinístico.
            plan.phase = PhaseEngine.execute(goal, week_start)

            repository.save(profile, plan)

            return plan

        except Exception as e:

            # IA fora do ar / plano inválido: nunca deixa o atleta sem plano
            print(
                f"IA falhou no plano de '{profile}', "
                f"fallback determinístico: {e}"
            )

            return AIPlanService._deterministic(
                profile, runner, assessment, metrics, goal,
                history, reference_date,
            )

    @staticmethod
    def _build_context(
        profile, runner, metrics, goal, history,
        repository, week_start, run_walk,
    ) -> str:

        # "plano anterior" = o da SEMANA ANTERIOR (a que acabou), NÃO o da
        # semana que estamos gerando. Antes vinha o plano guardado (o da
        # semana-alvo, futura): o resumo do executado casava as sessões
        # futuras contra zero atividade -> "zerou a semana" -> plano
        # cauteloso demais (bug do Renato/Fernanda: "após uma semana zerada"
        # mesmo tendo treinado). Vem do histórico, semana < alvo.
        last_week_plan = AIPlanService._previous_week_plan(
            repository,
            profile,
            week_start,
        )

        baseline = RunnerBaselineBuilder.build(history, runner)

        recent_adherence = WeeklyPlanService._recent_adherence(
            profile,
            repository,
            history,
            week_start,
        )

        memory = RunnerMemoryService.render(profile)

        weeks_to_race = AIPlanService._weeks_to_race(goal, week_start)

        executed = ExecutedWeekSummary.build(
            last_week_plan,
            history.activities,
        )

        return PlanContextBuilder.build(
            runner=runner,
            goal=goal,
            metrics=metrics,
            baseline=baseline,
            recent_adherence=recent_adherence,
            last_plan=last_week_plan,
            executed=executed,
            memory=memory,
            weeks_to_race=weeks_to_race,
            run_walk=run_walk,
        )

    @staticmethod
    def _previous_week_plan(repository, profile, week_start):
        """Plano da SEMANA ANTERIOR mais recente (week_start < alvo), do
        histórico. É contra ele que se mede o executado — nunca contra o da
        semana-alvo (que ainda não aconteceu)."""

        past = [
            plan
            for plan in repository.history(profile)
            if plan.week_start < week_start
        ]

        if not past:

            return None

        return max(past, key=lambda plan: plan.week_start)

    @staticmethod
    def _weeks_to_race(goal: TrainingGoal, week_start: date) -> int | None:

        if goal.race_date is None or goal.race_date <= week_start:

            return None

        return (goal.race_date - week_start).days // 7

    @staticmethod
    def _deterministic(
        profile, runner, assessment, metrics, goal,
        history, reference_date,
    ) -> TrainingPlan:

        return WeeklyPlanService.get_or_generate(
            profile=profile,
            runner=runner,
            assessment=assessment,
            metrics=metrics,
            goal=goal,
            reference_date=reference_date,
            history=history,
        )
