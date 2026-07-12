from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.history.metrics_resolver import MetricsResolver
from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.application.coach.planning.ai_plan_service import AIPlanService
from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import today_local
from app.application.garmin.garmin_sync import GarminSync
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.infrastructure.integrations.garmin.garmin_offer_store import (
    GarminOfferStore,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


class WeeklyPlanNotifier:

    @staticmethod
    async def notify_all() -> None:

        for profile in RunnerProfileRepository().list_all():

            try:

                await WeeklyPlanNotifier._notify_one(profile)

            except Exception as e:

                print(
                    f"Falha ao enviar plano semanal para "
                    f"'{profile}': {e}",
                )

    @staticmethod
    async def _notify_one(
        profile: str,
    ) -> None:

        runner = LoadRunnerProfile.execute(profile)

        # atleta com treinador humano: pede o treino da semana em vez
        # de gerar plano
        if runner.external_coach:

            await WeeklyPlanNotifier._notify_external(
                profile,
                runner,
            )

            return

        history = await LoadTrainingHistory.execute(
            profile=profile,
        )

        assessment = TrainingAssessmentBuilder.build(
            runner,
            history,
        )

        metrics = MetricsResolver.resolve(
            runner,
            history,
        )

        goal = BuildTrainingGoal.execute(runner)

        plan = await AIPlanService.ensure_plan(
            profile=profile,
            runner=runner,
            assessment=assessment,
            metrics=metrics,
            goal=goal,
            history=history,
        )

        message = WeeklyPlanMessageFormatter.format(
            runner.name,
            plan,
        )

        # atleta com Garmin conectado: oferece mandar os treinos pro
        # relógio. Marca a oferta como pendente pra entender o "SIM".
        if GarminSync.should_offer(profile, runner):

            message += GarminSync.offer_text()

            GarminOfferStore.set_pending(profile)

        await NotificationService.send(
            runner,
            message,
        )

    @staticmethod
    async def remind_external_pending() -> None:
        """Segunda de manhã: reforça o pedido do treino da semana pro atleta
        de treinador externo que AINDA não mandou (sem plano registrado desta
        semana). Sem esse print, a semana começa sem plano — e a análise fica
        sem a prescrição pra comparar. Falha de um atleta não derruba os
        outros."""

        for profile in RunnerProfileRepository().list_all():

            try:

                runner = LoadRunnerProfile.execute(profile)

                if not runner.external_coach:

                    continue

                if WeeklyPlanNotifier._has_current_week_plan(profile):

                    continue

                await NotificationService.send(
                    runner,
                    WeeklyPlanNotifier._reminder_text(runner.name),
                )

            except Exception as e:

                print(
                    f"Falha no lembrete de plano externo '{profile}': {e}"
                )

    @staticmethod
    def _has_current_week_plan(profile: str) -> bool:

        plan = WeeklyPlanRepository().load(profile)

        current_week = WeeklyPlanService._week_start(today_local())

        return plan is not None and plan.week_start == current_week

    @staticmethod
    def _reminder_text(name: str) -> str:

        return (
            f"Oi, {name}! 🏃 Ainda não recebi o treino desta semana do seu "
            "treinador. Quando puder, me manda o print, foto ou PDF que eu "
            "acompanho e te dou o feedback certinho. 📸"
        )

    @staticmethod
    async def _notify_external(
        profile: str,
        runner,
    ) -> None:

        plan = WeeklyPlanRepository().load(profile)

        current_week = WeeklyPlanService._week_start(today_local())

        if plan is not None and plan.week_start == current_week:

            # plano da semana já enviado: só reapresenta
            message = WeeklyPlanMessageFormatter.format(
                runner.name,
                plan,
            )

        else:

            message = (
                f"Bom domingo, {runner.name}! 🏃\n\n"
                "Me manda um print, foto ou PDF do treino da semana "
                "que vem (começa segunda) do seu treinador pra eu "
                "acompanhar seus treinos e te dar feedback. 📸"
            )

        await NotificationService.send(
            runner,
            message,
        )
