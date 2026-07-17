"""Late connector: atleta que conectou o Strava DEPOIS de terminar o
cadastro. No cadastro sem Strava o plano saiu conservador (histórico
vazio); agora que o histórico chegou, o coach regenera o plano da semana
com o retrato real e manda pro atleta na hora.

Uma vez só (marcador anti-spam) — reconexões não re-disparam. Vale só pra
plano do RunMind: quem treina com treinador externo recebe o plano do
treinador, então aqui o Strava entra só como histórico/contexto."""

from app.application.coach.intelligence.personal_record_detector import (
    PersonalRecordDetector,
)
from app.application.garmin.garmin_sync import GarminSync
from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.planner.current_plan_provider import (
    CurrentPlanProvider,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import today_local
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.integrations.garmin.garmin_offer_store import (
    GarminOfferStore,
)
from app.infrastructure.persistence.strava_refresh_store import (
    StravaRefreshStore,
)


class StravaConnectRefresh:

    @staticmethod
    async def refresh(profile: str) -> None:
        """Roda em background após a conexão do Strava. Falha aqui nunca
        derruba a conexão (o callback já respondeu) — só loga."""

        try:

            await StravaConnectRefresh._refresh(profile)

        except Exception as e:

            print(
                f"Falha ao regenerar plano de '{profile}' na conexão "
                f"do Strava: {e}"
            )

    @staticmethod
    async def _refresh(profile: str) -> None:

        runner = LoadRunnerProfile.execute(profile)

        # Semeia os recordes com o histórico real AGORA — assim o primeiro
        # treino de verdade do atleta já compara (e comemora) direito, em
        # vez de "gastar" o primeiro ciclo só estabelecendo a base. Isolado:
        # falha aqui nunca pode bloquear a regeneração do plano abaixo.
        try:

            await PersonalRecordDetector.seed(profile)

        except Exception as e:

            print(f"Falha ao semear recordes de '{profile}': {e}")

        # Treinador externo: o plano é do treinador; o Strava entra só como
        # histórico/contexto. Arquiva e sai — não gera nem envia plano.
        if runner.external_coach:

            await LoadTrainingHistory.execute(profile=profile)

            return

        # Uma vez só: reconexões não re-disparam plano/mensagem. Ainda assim
        # mantém o histórico arquivado a cada conexão.
        if StravaRefreshStore.is_done(profile):

            await LoadTrainingHistory.execute(profile=profile)

            return

        # Regenera o plano da SEMANA ATUAL pela IA com o histórico real
        # (force: por cima do plano conservador do cadastro). O provider já
        # carrega e arquiva o histórico do Strava.
        runner, plan = await CurrentPlanProvider.for_profile(
            profile,
            force=True,
        )

        message = StravaConnectRefresh._message(runner.name, plan)

        # Tem Garmin conectado? oferece mandar pro relógio — mesmo fluxo do
        # plano de domingo (marca a oferta pendente pra entender o "SIM").
        if GarminSync.should_offer(profile, runner):

            message += GarminSync.offer_text()

            GarminOfferStore.set_pending(profile)

        await NotificationService.send(runner, message)

        StravaRefreshStore.mark(profile)

    @staticmethod
    def _message(name: str, plan: TrainingPlan) -> str:

        # dias já passados desta semana ficam marcados (não vira "vá fazer"
        # um treino cuja data já passou)
        sessions_text = "\n".join(
            WeeklyPlanMessageFormatter.session_lines(
                plan,
                reference_date=today_local(),
                past_label="⏭️ (já passou)",
            )
        ).strip()

        return (
            f"Boa, {name}! ⚡ Agora que seu Strava está conectado, refiz "
            "seu plano da semana com base no seu histórico real de "
            "corridas:\n\n"
            f"{sessions_text}"
        )
