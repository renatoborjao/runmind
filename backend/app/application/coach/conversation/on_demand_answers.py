from app.application.coach.conversation.intent_router import (
    ChatIntent,
)
from app.application.coach.intelligence.body_reading_service import (
    BodyReadingService,
)
from app.application.coach.intelligence.fitness_reading_service import (
    FitnessReadingService,
)
from app.application.coach.intelligence.state_portrait_service import (
    StatePortraitService,
)
from app.application.coach.planning.body_conduct_proposer import (
    BodyConductProposer,
)
from app.application.coach.planning.race_strategy_engine import (
    RaceStrategyEngine,
)
from app.application.coach.writer.body_reading_writer import (
    BodyReadingWriter,
)
from app.application.coach.writer.fitness_evolution_writer import (
    FitnessEvolutionWriter,
)
from app.application.coach.writer.help_menu import HelpMenu
from app.application.coach.writer.state_portrait_writer import (
    StatePortraitWriter,
)
from app.application.history.metrics_resolver import MetricsResolver
from app.application.orchestrators.last_training_report import (
    LastTrainingReport,
)
from app.application.planner.current_plan_provider import (
    CurrentPlanProvider,
)
from app.application.planner.weekly_plan_matcher import (
    WeeklyPlanMatcher,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import today_local
from app.core.config import get_settings
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_load import LOAD_INSUFFICIENT


class OnDemandAnswers:
    """Respostas canônicas e completas para perguntas com dado pronto no
    sistema — devolvidas sem passar pelo Gemini, para não resumir nem
    desconfigurar. None = não há resposta determinística (segue no chat)."""

    @staticmethod
    async def answer(
        intent: ChatIntent,
        profile: str,
        runner: RunnerProfile,
    ) -> str | None:

        if intent == ChatIntent.LAST_TRAINING:

            # None quando não há treino registrado — cai no Gemini, que
            # responde com naturalidade a partir do contexto.
            return await LastTrainingReport.build(profile)

        if intent == ChatIntent.NEXT_TRAINING:

            _, plan = await CurrentPlanProvider.for_profile(profile)

            # pula as sessões já cumpridas (mesmo fora de ordem)
            history = await LoadTrainingHistory.execute(profile=profile)

            done_days = WeeklyPlanMatcher.fulfilled_days(
                plan,
                history.activities,
            )

            return WeeklyPlanMessageFormatter.next_session_message(
                runner.name,
                plan,
                done_days=done_days,
            )

        if intent == ChatIntent.WEEKLY_PLAN:

            _, plan = await CurrentPlanProvider.for_profile(profile)

            # valida contra o histórico real: o que foi de fato treinado
            # aparece como feito; o resto do passado, como não feito
            history = await LoadTrainingHistory.execute(profile=profile)

            done_days = WeeklyPlanMatcher.fulfilled_days(
                plan,
                history.activities,
            )

            return WeeklyPlanMessageFormatter.week_plan_message(
                runner.name,
                plan,
                done_days=done_days,
            )

        if intent == ChatIntent.BODY_READING:

            # o service lê o corpo E grava/compara com o histórico (trajetória)
            reading, trajectory = BodyReadingService.read(profile)

            # sem recuperação (não tem Garmin) E sem carga suficiente: não há
            # leitura útil — cai no Gemini, que responde com naturalidade
            if (
                not reading.recovery.has_data
                and reading.load.status == LOAD_INSUFFICIENT
            ):

                return None

            # a trajetória só entra na MENSAGEM atrás da flag (modo observação);
            # a gravação já aconteceu independente disso
            note = (
                trajectory
                if get_settings().body_trajectory_in_message_enabled
                else None
            )

            text = await BodyReadingWriter.write(
                reading, runner.name, trajectory=note
            )

            # se o corpo pede freio e AMANHÃ tem treino exigente, o coach já
            # emenda a proposta de aliviar/remanejar (o 'sim' aplica). Best-
            # effort: nunca derruba a leitura do corpo.
            offer = await OnDemandAnswers._body_conduct_offer(
                profile, runner, reading, trajectory,
            )

            return f"{text}\n\n{offer}" if offer else text

        if intent == ChatIntent.FITNESS_TREND:

            # eixo "estou evoluindo?": veredito COMBINADO (EF + VO₂máx +
            # FC-repouso + arco longo). None (nenhum sinal com lastro) cai no
            # Gemini, que responde com naturalidade a partir do contexto.
            evolution = FitnessReadingService.read_evolution(profile)

            return FitnessEvolutionWriter.write(evolution, runner.name)

        if intent == ChatIntent.STATE_PORTRAIT:

            # retrato ÚNICO: corpo & carga + forma cruzados num panorama só.
            # None (nenhum eixo com lastro) cai no Gemini, que responde a
            # partir do contexto.
            reading, evolution = StatePortraitService.read(profile)

            return StatePortraitWriter.write(reading, evolution, runner.name)

        if intent == ChatIntent.RACE_STRATEGY:

            goal = BuildTrainingGoal.execute(runner)

            history = await LoadTrainingHistory.execute(profile=profile)

            metrics = MetricsResolver.resolve(runner, history)

            message = RaceStrategyEngine.build(runner.name, goal, metrics)

            # sem distância/tempo e sem forma pra estimar: pede o alvo
            if message is None:

                return (
                    "Bora montar sua estratégia de prova! 🏁 Me diz a "
                    "distância e um tempo-alvo (ex.: '10 km em 50 min') que "
                    "eu te passo o pace e os splits."
                )

            return message

        if intent == ChatIntent.HELP:

            # cardápio de descoberta — o que dá pra perguntar ao bot
            return HelpMenu.card(runner.name)

        return None

    @staticmethod
    async def _body_conduct_offer(
        profile, runner, reading, trajectory,
    ) -> str | None:

        try:

            _, plan = await CurrentPlanProvider.for_profile(profile)

            history = await LoadTrainingHistory.execute(profile=profile)

            return await BodyConductProposer.propose(
                profile, runner, plan, reading, trajectory,
                history, today_local(),
            )

        except Exception as e:

            print(f"Proposta de conduta (on-demand) falhou p/ '{profile}': {e}")

            return None
