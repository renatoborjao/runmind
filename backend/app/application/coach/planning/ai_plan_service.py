from datetime import date, timedelta

from app.application.coach.conversation.rpe_flow import RpeFlow
from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
)
from app.application.coach.intelligence.checkin_service import CheckinService
from app.application.coach.intelligence.fitness_reading_service import (
    FitnessReadingService,
)
from app.application.coach.memory.coach_learning_service import (
    CoachLearningService,
)
from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)
from app.application.coach.planning.body_directive import body_plan_directive
from app.application.coach.planning.coach_plan_engine import CoachPlanEngine
from app.application.coach.planning.executed_week_summary import (
    ExecutedWeekSummary,
)
from app.application.coach.planning.fitness_directive import (
    fitness_plan_directive,
)
from app.application.coach.planning.plan_context_builder import (
    PlanContextBuilder,
)
from app.application.history.adherence_analyzer import AdherenceAnalyzer
from app.application.history.runner_baseline_builder import (
    RunnerBaselineBuilder,
)
from app.application.planner.engines.phase_engine import PhaseEngine
from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.core.clock import today_local
from app.core.config import get_settings
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

        # últimas semanas de plano — pra a IA VER os tipos recentes e variar
        recent_plans = AIPlanService._recent_plans(
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

        # padrão de furo das últimas semanas — a janela vai até a semana
        # ANTERIOR à que estamos gerando (a nova ainda não aconteceu)
        adherence_report = AdherenceAnalyzer.analyze(
            repository.history(profile),
            history,
            until_week=week_start - timedelta(days=7),
        )

        memory = RunnerMemoryService.render(profile)

        # aprendizados do coach (o que ele FEZ) — só injeta com a flag ligada.
        # Desligada (padrão), passa "" e o prompt fica idêntico ao de hoje.
        learnings = (
            CoachLearningService.render(profile)
            if get_settings().coach_learning_inject_enabled
            else ""
        )

        weeks_to_race = AIPlanService._weeks_to_race(goal, week_start)

        executed = ExecutedWeekSummary.build(
            last_week_plan,
            history.activities,
        )

        # o corpo AGORA (carga à luz da recuperação): se pede freio, vira
        # diretriz de dose pra IA decidir a semana. Best-effort — falhar aqui
        # nunca deixa o atleta sem plano.
        body_directive = AIPlanService._body_directive(profile, weeks_to_race)

        # a FORMA (o atleta está evoluindo?): eficiência aeróbica subindo ->
        # progride; estagnada -> já traz o estímulo que fura o platô; caindo ->
        # alivia. O plano é dinâmico, a IA já propõe — não pergunta ao atleta.
        fitness_directive = AIPlanService._fitness_directive(profile)

        # AUTO-CALIBRAÇÃO: se o atleta vem sistematicamente mais devagar (ou mais
        # rápido) que o pace prescrito nos tiros, ajusta o alvo ao que ele
        # SUSTENTA — com evidência real. Anexa à diretriz de forma (mesmo eixo:
        # como prescrever o ritmo). Best-effort.
        calibration = AIPlanService._calibration_directive(profile)

        if calibration:

            fitness_directive = (
                f"{fitness_directive}\n{calibration}"
                if fitness_directive
                else calibration
            )

        return PlanContextBuilder.build(
            runner=runner,
            goal=goal,
            metrics=metrics,
            baseline=baseline,
            recent_adherence=recent_adherence,
            last_plan=last_week_plan,
            recent_plans=recent_plans,
            executed=executed,
            memory=memory,
            weeks_to_race=weeks_to_race,
            run_walk=run_walk,
            adherence_report=adherence_report,
            learnings=learnings,
            body_directive=body_directive,
            fitness_directive=fitness_directive,
        )

    @staticmethod
    def _body_directive(profile: str, weeks_to_race: int | None = None) -> str:
        """Sinais de ESTADO pra a dose: o objetivo (carga à luz da recuperação,
        do Garmin) + o subjetivo (o que o atleta RELATOU sentir). Os dois
        contam — o relógio não sente o que o atleta sente. Best-effort."""

        parts = []

        body_reading = None

        try:

            reading, trajectory = BodyReadingService.read(
                profile, persist=False
            )

            body_reading = reading

            parts.append(body_plan_directive(reading, trajectory))

        except Exception as e:

            print(f"Diretriz de corpo falhou p/ '{profile}': {e}")

        # RISCO DE LESÃO precoce: spike de carga (ACWR) + rampa de volume +
        # recuperação caindo + histórico → o coach constrói uma semana mais
        # segura (prevenção), antes de virar lesão. Best-effort.
        try:

            if body_reading is not None:

                from app.application.history.injury_risk_analyzer import (
                    InjuryRiskAnalyzer,
                    injury_risk_directive,
                )
                from app.infrastructure.persistence.form_fatigue_store import (
                    FormFatigueStore,
                )
                from app.infrastructure.persistence.runner_profile_repository import (
                    RunnerProfileRepository,
                )

                runner = RunnerProfileRepository().load(profile)

                risk = InjuryRiskAnalyzer.assess(
                    body_reading.load,
                    body_reading.recovery,
                    getattr(runner, "injuries", None),
                    form_fading=FormFatigueStore().is_fading(profile),
                )

                parts.append(injury_risk_directive(risk))

        except Exception as e:

            print(f"Diretriz de risco de lesão falhou p/ '{profile}': {e}")

        # DESCARGA proativa (recuperação PLANEJADA): depois de ~3 semanas de
        # carga sem recuo, a próxima é leve de propósito — o corpo consolida a
        # forma. Complementa o risco de lesão (reativo) com prevenção. Reusa a
        # série de carga semanal já lida acima. Best-effort.
        try:

            if body_reading is not None:

                from app.application.history.deload_analyzer import (
                    DeloadAnalyzer,
                    deload_directive,
                )

                decision = DeloadAnalyzer.assess(
                    body_reading.load.weekly_loads,
                    body_reading.recovery,
                    weeks_to_race=weeks_to_race,
                )

                parts.append(deload_directive(decision))

        except Exception as e:

            print(f"Diretriz de descarga falhou p/ '{profile}': {e}")

        try:

            parts.append(CheckinService.render_recent(profile))

        except Exception as e:

            print(f"Estado relatado falhou p/ '{profile}': {e}")

        try:

            parts.append(RpeFlow.recent_note(profile))

        except Exception as e:

            print(f"Nota de sRPE falhou p/ '{profile}': {e}")

        # o CUSTO do sono no desempenho dele — se o sono curto faz o pace cair
        # no mesmo esforço, o coach pesa isso na dose (protege dívida de sono)
        try:

            from app.application.history.sleep_performance_analyzer import (
                SleepPerformanceAnalyzer,
                sleep_impact_plan_directive,
            )
            from app.infrastructure.persistence.activity_archive_repository import (
                ActivityArchiveRepository,
            )
            from app.infrastructure.persistence.garmin_health_repository import (
                GarminHealthRepository,
            )

            impact = SleepPerformanceAnalyzer.analyze(
                ActivityArchiveRepository().load_activities(profile),
                GarminHealthRepository().load(profile),
            )

            parts.append(sleep_impact_plan_directive(impact))

        except Exception as e:

            print(f"Diretriz de sono falhou p/ '{profile}': {e}")

        return "\n".join(p for p in parts if p)

    @staticmethod
    def _fitness_directive(profile: str) -> str:
        """Diretriz de FORMA pra dose: a eficiência aeróbica (velocidade/FC)
        ao longo das semanas vira instrução pra IA progredir/furar platô/
        aliviar — o plano se adapta à evolução do atleta sem perguntar.
        Best-effort — falhar aqui nunca deixa o atleta sem plano."""

        try:

            evolution = FitnessReadingService.read_evolution(profile)

            return fitness_plan_directive(evolution)

        except Exception as e:

            print(f"Diretriz de forma falhou p/ '{profile}': {e}")

            return ""

    @staticmethod
    def _calibration_directive(profile: str) -> str:
        """Auto-calibração do pace: viés sistemático (prescrito × sustentado nos
        tiros) vira instrução pra ajustar o alvo de qualidade ao real. Best-
        effort — falhar aqui nunca deixa o atleta sem plano."""

        try:

            from app.application.history.pace_calibration_analyzer import (
                PaceCalibrationAnalyzer,
                calibration_directive,
            )
            from app.infrastructure.persistence.pace_calibration_store import (
                PaceCalibrationStore,
            )

            deltas = PaceCalibrationStore().deltas(profile)

            return calibration_directive(PaceCalibrationAnalyzer.assess(deltas))

        except Exception as e:

            print(f"Diretriz de calibração falhou p/ '{profile}': {e}")

            return ""

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
    def _recent_plans(repository, profile, week_start, limit: int = 4):
        """As últimas `limit` semanas de plano (week_start < alvo), em ordem
        cronológica. A IA lê os TIPOS recentes pra VARIAR o estímulo em vez de
        repetir o mesmo trio semana após semana."""

        past = sorted(
            (
                plan
                for plan in repository.history(profile)
                if plan.week_start < week_start
            ),
            key=lambda plan: plan.week_start,
        )

        return past[-limit:]

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
