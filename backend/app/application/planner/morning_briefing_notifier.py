import asyncio
from datetime import date, datetime, time, timedelta

from app.application.coach.planning.body_conduct_proposer import (
    BodyConductProposer,
)
from app.application.garmin.garmin_health_poller import GarminHealthPoller
from app.application.notifications.coach_outbox import (
    CoachOutbox,
)
from app.application.planner.briefing_deadline import BriefingDeadline
from app.application.planner.daily_training_notifier import (
    DailyTrainingNotifier,
)
from app.application.planner.missed_workout_flow import MissedWorkoutFlow
from app.application.review.readiness_notifier import ReadinessNotifier
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.core.clock import now_in, today_local, use_athlete_timezone
from app.domain.value_objects.sports import is_run_sport
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.integrations.garmin.garmin_health_source import (
    GarminHealthSource,
)
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.dispatch_guard import DispatchGuard
from app.infrastructure.persistence.garmin_health_repository import (
    GarminHealthRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# Janela de VIGÍLIA do despertar (hora local): o coach fica esperando o dado da
# noite chegar. Roda a cada TICK (o scheduler), mas só age nesta faixa. O fim
# vai até 11h30 pra dar folga aos ticks do teto das 11h (abaixo).
WINDOW_START = time(4, 30)
WINDOW_END = time(11, 30)

# Rede das 06h — só pra quem NÃO tem relógio: não há dado da noite pra esperar,
# então manda furo + treino cedo (ou antes, se ele costuma treinar mais cedo).
FALLBACK = time(6, 0)

# Teto da espera pelo sono — só pra quem TEM Garmin e NÃO treina de manhã: o
# treino está longe, então dá pra segurar o briefing inteiro até o dado da
# noite sincronizar. Passou daqui, desiste e manda sem o corpo.
LAST_RESORT = time(11, 0)

# Prazo de quem ainda não tem histórico de corrida (não sabemos a hora do
# treino): cedo o bastante pra chegar antes de um treino de manhã.
NO_HISTORY_DEADLINE = time(7, 0)

# Intervalo do job (weekly_plan_scheduler): curto pra o "bom dia" sair poucos
# minutos depois de o sono sincronizar (a espera usa a sonda de 1 chamada, não
# o retrato completo). O prazo é o limite MÁXIMO: decide no último tick ANTES
# dele — senão o envio escorregava até um tick inteiro depois.
TICK = timedelta(minutes=5)


class MorningBriefingNotifier:
    """"Bom dia" do despertar, numa mensagem só, por atleta. O gatilho é o dado
    da noite (sono/HRV) CHEGAR do Garmin — ou seja, o atleta acordou e o relógio
    sincronizou. Aí o coach fala fresco e ANTES do treino, cedo ou tarde:

      1) furo de ONTEM (se houve),
      2) corpo de HOJE: prontidão (CAUTION/GREEN, atrás da flag) OU, em
         sobrecarga, a PROPOSTA de aliviar o treino de hoje,
      3) treino de HOJE (suprimido quando a proposta já o descreve).

    Blocos independentes: cada um só entra se tiver o que dizer. Quem TEM Garmin
    segura o briefing inteiro até o SONO da noite sincronizar — mas o treino não
    espera o sync: o PRAZO é pessoal (BriefingDeadline — 20 min antes do horário
    em que ele costuma treinar naquele dia da semana; teto 11h pra quem treina à
    tarde/noite). Estourou o prazo, sai furo + treino sem o corpo, e o corpo vem
    como COMPLEMENTO quando o sono chegar (se ainda não treinou e se houver o que
    dizer). Quem NÃO tem relógio recebe furo + treino na rede das 06h (ou antes,
    pelo mesmo prazo). Ver [[project_analise_corpo_garmin]]."""

    @staticmethod
    async def notify_all() -> None:
        """Roda a cada ~15 min; cada _notify_one decide, no fuso do atleta, se
        já é hora e se o dado da noite chegou. Dedup: um 'bom dia' por dia."""

        for profile in RunnerProfileRepository().list_active():

            try:

                await MorningBriefingNotifier._notify_one(profile)

            except Exception as e:

                print(f"Briefing matinal falhou para '{profile}': {e}")

    @staticmethod
    async def _notify_one(profile: str) -> None:

        # medidor de tokens: atribui o Gemini do briefing deste atleta a ele
        from app.application.monitoring.token_meter import TokenMeter

        TokenMeter.set_current(profile, "briefing")

        runner = LoadRunnerProfile.execute(profile)

        # fuso do atleta primeiro: ontem/hoje/semana no horário dele
        use_athlete_timezone(runner.timezone)

        local = now_in(runner.timezone)

        # fora da janela da manhã não faz nada (barato o resto do dia)
        if not (WINDOW_START <= local.time() <= WINDOW_END):

            return

        # o dia da PROVA é do companheiro de prova (o "É HOJE! 🏁"): o briefing
        # de rotina CEDE o dia — nada de tratar a prova-alvo como "mais um
        # treino" com clima "boas pra treinar". Era a queixa do Renato.
        if MorningBriefingNotifier._is_race_day(runner):

            return

        period = local.date().isoformat()

        has_garmin = (
            GarminClient.is_connected(profile)
            and GarminClient.analysis_enabled(profile)
        )

        # já mandou o 'bom dia' de hoje — resta só o complemento do corpo, se o
        # briefing saiu sem o sono (estourou o prazo antes do sync)
        if DispatchGuard.already_sent("briefing", profile, period):

            if has_garmin:

                await MorningBriefingNotifier._body_followup(
                    runner, profile, period, local.date()
                )

            return

        # Quando enviar?
        #  • COM Garmin: SEGURA o briefing inteiro (furo + corpo + treino) até o
        #    SONO da noite chegar — pra não soltar o "bom dia" sem o corpo de
        #    quem tem como medir. Mas só até o PRAZO pessoal (antes do horário
        #    habitual de treino dele): aí manda sem o corpo, que vem depois.
        #  • SEM relógio: não há dado pra esperar — rede das 06h (ou o prazo
        #    pessoal, se ele treina mais cedo que isso).
        deadline = MorningBriefingNotifier._deadline(profile, local.date())

        # último tick que ainda chega antes do prazo
        send_by = (datetime.combine(local.date(), deadline) - TICK).time()

        data_ready = False

        if has_garmin:

            # rede síncrona do Garmin em thread (não trava o servidor)
            data_ready = await asyncio.to_thread(
                MorningBriefingNotifier._night_data_ready, profile, local.date()
            )

            if not data_ready and local.time() < send_by:

                return

        elif local.time() < min(FALLBACK, send_by):

            return

        # commit da decisão do dia: o sono chegou (despertar), ou estourou o
        # prazo (Garmin), ou a rede das 06h (sem relógio). Marca já pra não
        # reprocessar a cada tick.
        DispatchGuard.mark("briefing", profile, period)

        # saiu sem o sono de quem tem relógio: o corpo fica devendo (complemento)
        if has_garmin and not data_ready:

            DispatchGuard.mark("briefing_body_due", profile, period)

        parts: list[str] = []

        # 1) furo de ONTEM (pode guardar uma proposta pro 'sim')
        missed = await MissedWorkoutFlow.process(profile)

        if missed is not None:

            parts.append(missed[1])

        # 2) corpo de HOJE — só quando o dado da noite chegou (ver _body_part).
        proposal = None

        # a leitura de corpo (ReadinessNotifier.block) sempre abre com "Bom
        # dia!"; se ela entra, o treino logo abaixo NÃO repete a saudação.
        greeted = False

        if data_ready:

            body, is_proposal = await MorningBriefingNotifier._body_part(profile)

            if body:

                parts.append(body)

                if is_proposal:

                    proposal = body

                else:

                    greeted = True

        # 3) treino de HOJE (descanso volta None) — MAS se a proposta STRAINED
        #    já falou do treino de hoje, não repete (ela já o descreve). Só
        #    cumprimenta se o corpo já não cumprimentou (evita dois "bom dia").
        if proposal is None:

            today = await DailyTrainingNotifier.build(profile, greet=not greeted)

            if today is not None:

                # o treino já vem COM a linha de clima do dia (uma só,
                # DailyTrainingNotifier._weather_line: calor rico OU geral).
                # Não adicionamos outra aqui — antes saíam duas linhas de
                # calor na mesma mensagem (a queixa do Renato).
                parts.append(today[1])

        # nada a dizer (sem furo, sem alerta, hoje é descanso): silêncio
        if not parts:

            return

        # "bom dia" do despertar sai só em TEXTO: é a mensagem diária mais
        # longa (furo + corpo + treino), e um áudio disso todo dia cansa. A
        # voz fica reservada pros beats curtos que emocionam (prova, recorde).
        await CoachOutbox.send(
            runner, "\n\n".join(parts), profile=profile, kind="morning_briefing",
        )

    @staticmethod
    async def _body_part(profile: str) -> tuple[str | None, bool]:
        """O bloco de corpo de HOJE (com o sono da noite já ingerido). É UM
        bloco: prontidão (CAUTION/GREEN, atrás da flag) OU, se o corpo está em
        SOBRECARGA, a PROPOSTA de aliviar o treino de hoje. Nunca os dois
        (STRAINED cala a prontidão), então nunca infla. Volta (texto, é_proposta);
        (None, False) quando o corpo não tem o que dizer."""

        block = await ReadinessNotifier.block(profile)

        if block:

            return block, False

        proposal = await BodyConductProposer.for_briefing(profile)

        if proposal:

            return proposal, True

        return None, False

    @staticmethod
    async def _body_followup(
        runner, profile: str, period: str, day: date,
    ) -> None:
        """COMPLEMENTO do corpo: o briefing saiu no prazo SEM o sono (o sync
        atrasou) e o sono chegou depois. Manda só o bloco de corpo — e só se
        ele ainda não treinou (depois do treino, a análise já fala do dia) e se
        o corpo tem o que dizer (mesmo gate do briefing: momento novo). Uma
        decisão por dia."""

        if not DispatchGuard.already_sent("briefing_body_due", profile, period):

            return

        if DispatchGuard.already_sent("briefing_body", profile, period):

            return

        data_ready = await asyncio.to_thread(
            MorningBriefingNotifier._night_data_ready, profile, day
        )

        if not data_ready:

            return

        # commit: o sono chegou; decide agora, uma vez só
        DispatchGuard.mark("briefing_body", profile, period)

        if MorningBriefingNotifier._ran_today(profile, day):

            return

        body, _ = await MorningBriefingNotifier._body_part(profile)

        if not body:

            return

        await CoachOutbox.send(runner, body, profile=profile, kind="morning_body")

    @staticmethod
    def _deadline(profile: str, day: date) -> time:
        """Até quando esperar o sono hoje: 20 min antes do horário em que o
        atleta costuma treinar neste dia da semana (ver BriefingDeadline).
        Best-effort: falha ao ler o histórico cai no prazo sem histórico."""

        try:

            activities = ActivityArchiveRepository().load_activities(profile)

        except Exception as e:

            print(f"Prazo do briefing: histórico de '{profile}' falhou: {e}")

            activities = []

        return BriefingDeadline.compute(
            activities,
            day,
            floor=WINDOW_START,
            ceiling=LAST_RESORT,
            default=NO_HISTORY_DEADLINE,
        )

    @staticmethod
    def _ran_today(profile: str, day: date) -> bool:
        """Já tem corrida de HOJE no arquivo? (o treino já foi — o complemento
        do corpo chegaria tarde). Best-effort: na dúvida, não bloqueia."""

        try:

            return any(
                is_run_sport(a.sport) and a.start_date.date() == day
                for a in ActivityArchiveRepository().load_activities(profile)
            )

        except Exception:

            return False

    @staticmethod
    def _is_race_day(runner) -> bool:
        """Hoje é o dia da prova-alvo do atleta? Best-effort: qualquer falha ao
        montar o objetivo NÃO cala o briefing (volta False)."""

        try:

            goal = BuildTrainingGoal.execute(runner)

            return goal.race_date is not None and goal.race_date == today_local()

        except Exception:

            return False

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

        # O âncora é o SONO de hoje, não "existe registro de hoje": o poller de
        # recuperação (tick de 15 min) grava o dia corrente PARCIAL de madrugada
        # (stress/SpO2/bateria, às vezes HRV) antes do sono fechar. Checar só a
        # data fazia o "bom dia" sair no 1º tick da janela (~04h30), com o
        # atleta dormindo e sem o sono da noite (queixa do Renato, 29/09).
        existing = repo.get(profile, today_iso)

        if existing is not None and existing.sleep_hours is not None:

            return True

        try:

            # sonda de 1 chamada a cada tick; o retrato completo (9 chamadas)
            # só quando o sono fechou — gentil com a API não-oficial
            if not GarminHealthSource.sleep_closed(profile, today_iso):

                return False

            health = GarminHealthSource.fetch(profile, today_iso)

        except Exception as e:

            print(f"Fetch do sono da manhã falhou para '{profile}': {e}")

            return False

        # só considera "acordou" quando o SONO da noite está fechado (o HRV
        # sozinho pode ter sincronizado durante a madrugada, sem o atleta acordar)
        if health is None or health.sleep_hours is None:

            return False

        # mescla sobre o parcial da madrugada (não apaga o que o poller trouxe)
        repo.upsert(profile, GarminHealthPoller._merge(existing, health))

        return True
