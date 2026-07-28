from datetime import date, time

from app.application.notifications.coach_outbox import (
    CoachOutbox,
)
from app.application.planner.daily_training_notifier import (
    DailyTrainingNotifier,
)
from app.application.planner.missed_workout_flow import MissedWorkoutFlow
from app.application.review.readiness_notifier import ReadinessNotifier
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.core.clock import now_in, use_athlete_timezone
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.integrations.garmin.garmin_health_source import (
    GarminHealthSource,
)
from app.infrastructure.persistence.dispatch_guard import DispatchGuard
from app.infrastructure.persistence.garmin_health_repository import (
    GarminHealthRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# Janela de VIGÍLIA do despertar (hora local): o coach fica esperando o dado da
# noite chegar. Roda a cada ~15 min (o scheduler), mas só age nesta faixa.
WINDOW_START = time(4, 30)
WINDOW_END = time(10, 0)

# Rede de horário: se o dado da noite NÃO chegou (atleta sem relógio) até aqui,
# manda o briefing mesmo assim — sem o bloco de corpo. Ninguém fica sem "bom dia".
FALLBACK_HOUR = 6


class MorningBriefingNotifier:
    """"Bom dia" do despertar, numa mensagem só, por atleta. O gatilho é o dado
    da noite (sono/HRV) CHEGAR do Garmin — ou seja, o atleta acordou e o relógio
    sincronizou. Aí o coach fala fresco e ANTES do treino, cedo ou tarde:

      1) furo de ONTEM (se houve),
      2) leitura de corpo / prontidão de HOJE (se merece — atrás da flag),
      3) treino de HOJE.

    Blocos independentes: cada um só entra se tiver o que dizer. Sem relógio (sem
    dado até as 06h), manda furo + treino sem o bloco de corpo. Uma voz de manhã,
    não três. Ver [[project_analise_corpo_garmin]]."""

    @staticmethod
    async def notify_all() -> None:
        """Roda a cada ~15 min; cada _notify_one decide, no fuso do atleta, se
        já é hora e se o dado da noite chegou. Dedup: um 'bom dia' por dia."""

        for profile in RunnerProfileRepository().list_all():

            try:

                await MorningBriefingNotifier._notify_one(profile)

            except Exception as e:

                print(f"Briefing matinal falhou para '{profile}': {e}")

    @staticmethod
    async def _notify_one(profile: str) -> None:

        runner = LoadRunnerProfile.execute(profile)

        # fuso do atleta primeiro: ontem/hoje/semana no horário dele
        use_athlete_timezone(runner.timezone)

        local = now_in(runner.timezone)

        # fora da janela da manhã não faz nada (barato o resto do dia)
        if not (WINDOW_START <= local.time() <= WINDOW_END):

            return

        period = local.date().isoformat()

        # já mandou o 'bom dia' de hoje
        if DispatchGuard.already_sent("briefing", profile, period):

            return

        data_ready = MorningBriefingNotifier._night_data_ready(
            profile, local.date()
        )

        # ainda cedo e o dado não chegou: espera o despertar (próximo tick)
        if not data_ready and local.hour < FALLBACK_HOUR:

            return

        # commit da decisão do dia: ou o dado chegou (despertar), ou passou da
        # rede das 06h. Marca já pra não reprocessar a cada tick.
        DispatchGuard.mark("briefing", profile, period)

        parts: list[str] = []

        # 1) furo de ONTEM (pode guardar uma proposta pro 'sim')
        missed = await MissedWorkoutFlow.process(profile)

        if missed is not None:

            parts.append(missed[1])

        # 2) corpo / prontidão de HOJE — só quando o dado da noite chegou e
        #    (atrás da flag) o estado merece voz
        if data_ready:

            block = await ReadinessNotifier.block(profile)

            if block:

                parts.append(block)

        # 3) treino de HOJE (descanso volta None)
        today = await DailyTrainingNotifier.build(profile)

        if today is not None:

            parts.append(today[1])

        # nada a dizer (sem furo, sem alerta, hoje é descanso): silêncio
        if not parts:

            return

        # "bom dia" do despertar sai só em TEXTO: é a mensagem diária mais
        # longa (furo + corpo + treino), e um áudio disso todo dia cansa. A
        # voz fica reservada pros beats curtos que emocionam (prova, recorde).
        await CoachOutbox.send(runner, "\n\n".join(parts))

    @staticmethod
    def _night_data_ready(profile: str, day: date) -> bool:
        """O sono/HRV DESTA noite já chegou do Garmin? É o sinal de que o atleta
        acordou e sincronizou. Sem Garmin conectado, nunca fica pronto (cai na
        rede das 06h, sem bloco de corpo). Idempotente: uma vez ingerido, o
        repositório responde sem bater na API de novo."""

        if not (
            GarminClient.is_connected(profile)
            and GarminClient.analysis_enabled(profile)
        ):

            return False

        repo = GarminHealthRepository()

        today_iso = day.isoformat()

        # já ingerimos o dado desta manhã num tick anterior
        if repo.has_date(profile, today_iso):

            return True

        try:

            health = GarminHealthSource.fetch(profile, today_iso)

        except Exception as e:

            print(f"Fetch do sono da manhã falhou para '{profile}': {e}")

            return False

        # só considera "acordou" quando o SONO da noite está fechado (o HRV
        # sozinho pode ter sincronizado durante a madrugada, sem o atleta acordar)
        if health is None or health.sleep_hours is None:

            return False

        repo.upsert(profile, health)

        return True
