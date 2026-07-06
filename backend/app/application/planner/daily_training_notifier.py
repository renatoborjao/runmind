from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.planner.current_plan_provider import (
    CurrentPlanProvider,
)
from app.application.planner.weather_advisor import WeatherAdvisor
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.domain.entities.training_history import TrainingHistory
from app.infrastructure.integrations.weather.open_meteo_client import (
    OpenMeteoClient,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


class DailyTrainingNotifier:
    """Lembrete matinal (06h): no dia em que há treino, manda a sessão
    detalhada + o clima do dia. Dia de descanso não gera mensagem."""

    @staticmethod
    async def notify_all() -> None:

        for profile in RunnerProfileRepository().list_all():

            try:

                await DailyTrainingNotifier._notify_one(profile)

            except Exception as e:

                print(
                    f"Falha no lembrete matinal para '{profile}': {e}",
                )

    @staticmethod
    async def _notify_one(
        profile: str,
    ) -> None:

        runner, plan = await CurrentPlanProvider.for_profile(profile)

        message = WeeklyPlanMessageFormatter.today_session_message(
            runner.name,
            plan,
        )

        # Dia de descanso: nada a enviar.
        if message is None:

            return

        weather = await DailyTrainingNotifier._weather_line(profile)

        if weather:

            message = f"{message}\n\n{weather}"

        await NotificationService.send(
            runner,
            message,
        )

    @staticmethod
    async def _weather_line(
        profile: str,
    ) -> str:
        """Linha de clima pro treino de hoje, da coordenada do último treino
        outdoor do atleta. Sem GPS (atleta novo/esteira) ou clima fora do ar
        -> string vazia (o lembrete sai sem a linha, nunca quebra)."""

        try:

            history = await LoadTrainingHistory.execute(profile=profile)

            coords = DailyTrainingNotifier._latest_coords(history)

            if coords is None:

                return ""

            forecast = await OpenMeteoClient.forecast_today(*coords)

            if forecast is None:

                return ""

            return WeatherAdvisor.line(forecast)

        except Exception as e:

            print(f"Clima do lembrete falhou para '{profile}': {e}")

            return ""

    @staticmethod
    def _latest_coords(
        history: TrainingHistory,
    ) -> tuple[float, float] | None:
        """Coordenada de partida do treino outdoor mais recente (onde o
        atleta corre de verdade). Treino de esteira não tem GPS."""

        outdoor = sorted(
            (
                activity
                for activity in history.activities
                if activity.start_latitude is not None
                and activity.start_longitude is not None
            ),
            key=lambda activity: activity.start_date,
            reverse=True,
        )

        if not outdoor:

            return None

        latest = outdoor[0]

        return (latest.start_latitude, latest.start_longitude)
