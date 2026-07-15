from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.history.metrics_resolver import MetricsResolver
from app.application.notifications.coach_outbox import (
    CoachOutbox,
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
from app.core.clock import now_in, today_local, use_athlete_timezone
from app.infrastructure.persistence.dispatch_guard import DispatchGuard
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


# domingo (weekday 6) 15h LOCAL: entrega do plano. Segunda (0) 8h: lembrete
# do treinador externo.
_SUNDAY = 6

_MONDAY = 0

PLAN_HOUR = 15

EXTERNAL_REMINDER_HOUR = 8


def _week_key(local) -> str:

    iso = local.isocalendar()

    return f"{iso[0]}-W{iso[1]:02d}"


class WeeklyPlanNotifier:

    @staticmethod
    async def notify_all() -> None:
        """Roda de HORA EM HORA; cada _notify_one decide se é o horário local
        do atleta (domingo 15h) e faz dedup."""

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

        use_athlete_timezone(runner.timezone)

        local = now_in(runner.timezone)

        # só no domingo 15h LOCAL do atleta, uma vez por semana (dedup)
        if local.weekday() != _SUNDAY or local.hour != PLAN_HOUR:

            return

        period = _week_key(local)

        if DispatchGuard.already_sent("weekly_plan", profile, period):

            return

        DispatchGuard.mark("weekly_plan", profile, period)

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

        # Entrega de domingo 15h: gera e anuncia o plano da PRÓXIMA semana.
        # Só a partir daqui ele vira a semana ativa do atleta (o cache >= o
        # devolve nas leituras seguintes) — nunca antes da entrega.
        plan = await AIPlanService.ensure_plan(
            profile=profile,
            runner=runner,
            assessment=assessment,
            metrics=metrics,
            goal=goal,
            history=history,
            reference_date=WeeklyPlanService.upcoming_week_start(),
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

        await CoachOutbox.send(
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

                use_athlete_timezone(runner.timezone)

                local = now_in(runner.timezone)

                # segunda 8h LOCAL, uma vez (dedup diário)
                if (
                    local.weekday() != _MONDAY
                    or local.hour != EXTERNAL_REMINDER_HOUR
                ):

                    continue

                if not runner.external_coach:

                    continue

                period = local.date().isoformat()

                if DispatchGuard.already_sent(
                    "external_reminder", profile, period
                ):

                    continue

                if WeeklyPlanNotifier._has_current_week_plan(profile):

                    continue

                await CoachOutbox.send(
                    runner,
                    WeeklyPlanNotifier._reminder_text(runner.name),
                )

                DispatchGuard.mark("external_reminder", profile, period)

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

        await CoachOutbox.send(
            runner,
            message,
        )
