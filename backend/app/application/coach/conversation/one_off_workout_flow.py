from dataclasses import replace
from datetime import date, timedelta

from app.application.coach.conversation.one_off_workout_detector import (
    OneOffWorkoutDetector,
)
from app.application.coach.planning.executed_week_summary import (
    ExecutedWeekSummary,
)
from app.application.coach.planning.one_off_workout_engine import (
    OneOffWorkoutEngine,
)
from app.application.garmin.push_one_off import push_one_off
from app.application.history.runner_portrait import build_portrait
from app.application.history.stimulus_ledger import StimulusLedger
from app.application.history.weekly_evolution_digest import (
    WeeklyEvolutionDigest,
)
from app.application.planner.current_plan_provider import CurrentPlanProvider
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import today_local
from app.core.weekdays import WEEKDAYS, weekday_label
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_plan import TrainingPlan
from app.domain.entities.workout_step import parse_steps
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.integrations.garmin.one_off_offer_store import (
    OneOffOfferStore,
)
from app.infrastructure.integrations.garmin.one_off_proposal_store import (
    OneOffProposalStore,
)
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)

_RUNNING_KINDS = {"run", "walk", "run_walk"}

# respostas curtas à oferta de mandar o avulso pro relógio
_AFFIRMATIVE = {
    "sim", "s", "quero", "quero sim", "pode", "pode ser", "isso", "bora",
    "manda", "claro", "ok", "aceito", "sim quero", "pode mandar", "yes",
    "sim!", "quero!", "bora!", "manda ai", "manda ver",
}

_NEGATIVE = {
    "nao", "nao quero", "agora nao", "depois", "deixa", "nem", "nao precisa",
    "pode deixar", "nao obrigado",
}


class OneOffWorkoutFlow:
    """Fluxo reativo do treino AVULSO: o atleta pede que o nosso coach monte
    um treino pra um dia específico que o plano não cobre (típico do atleta de
    treinador externo num dia que o treinador não gerou). Monta UMA sessão
    ancorada nos dados/evolução dele, grava no plano marcada como 'oneoff'
    (sem reescrever o resto) e oferece mandar pro relógio."""

    @staticmethod
    async def handle(
        profile: str,
        runner: RunnerProfile,
        incoming_text: str,
        athlete_context: str = "",
    ) -> str | None:

        if not OneOffWorkoutDetector.looks_like_request(incoming_text):

            return None

        return await OneOffWorkoutFlow.build_for(
            profile, runner, incoming_text, athlete_context=athlete_context,
        )

    @staticmethod
    async def build_for(
        profile: str,
        runner: RunnerProfile,
        incoming_text: str,
        athlete_context: str = "",
        forced_date: date | None = None,
        day_hint: str | None = None,
        commit_now: bool = False,
    ) -> str | None:
        """Núcleo SEM o portão de palavra-chave: resolve o dia, monta a sessão
        avulsa ancorada no histórico + estado atual do atleta e oferece o
        relógio. Usado pelo cérebro do coach (que já reconheceu o pedido) e pelo
        handle() determinístico (fallback). `forced_date` pula a resolução por
        texto — usado quando é uma CORREÇÃO de um avulso já montado ("não, 1km
        só"), em que o dia já é conhecido e o texto não tem data.
        `day_hint` é o dia (ex.: 'Sunday') que o cérebro leu da conversa.
        `commit_now` (pedido explícito de relógio) grava e manda sem perguntar.
        Ver [[project_roteador_acao_ia]]."""

        today = today_local()

        pending = OneOffProposalStore.pending(profile)

        # o dia: data explícita > texto > dia que o cérebro leu da conversa >
        # a proposta pendente (é AJUSTE dela: "bora aumentar pra 8km?"). Só
        # pergunta o dia quando nada disso existe — nunca em loop sobre um
        # treino que acabou de ser proposto (bug do Renato, 26/09).
        target_date = (
            forced_date
            or OneOffWorkoutDetector.resolve_target_date(incoming_text, today)
            or OneOffWorkoutFlow._date_for_day(day_hint, today)
            or (date.fromisoformat(pending["date"]) if pending else None)
        )

        if target_date is None:

            OneOffProposalStore.set_awaiting_day(profile, incoming_text)

            return (
                "Boa! Pra qual dia você quer o treino? "
                "(ex.: 'domingo', 'amanhã', '02/08') 🗓️"
            )

        # a resposta ao "pra qual dia?" ("amanhã") carrega o pedido que ficou
        # esperando — senão o motor recebe só a data e ignora o que foi pedido
        waiting = OneOffProposalStore.pop_awaiting_day(profile)

        request = (
            f"{waiting} — {incoming_text}" if waiting else incoming_text
        )

        if target_date < today:

            return (
                "Esse dia já passou 😅 me diz um dia daqui pra frente "
                "que eu monto."
            )

        _, plan = await CurrentPlanProvider.for_profile(profile)

        # v1: treino avulso só dentro da semana do plano vigente
        if not (
            plan.week_start
            <= target_date
            <= plan.week_start + timedelta(days=6)
        ):

            return (
                "Por enquanto eu monto treino avulso só pra esta semana 🙂 "
                "me pede de novo mais perto do dia."
            )

        target_day = WEEKDAYS[target_date.weekday()]

        existing = plan.find_session_by_day(target_day)

        # atleta NOSSO que já tem treino nesse dia: não duplica — aponta o que
        # já tem (se quiser mudar, é negociação/aversão). EXCEÇÃO: se o que já
        # está lá é um AVULSO nosso (origin='oneoff'), a gente REMONTA por cima
        # (é o caso da correção "não, 1km só" logo após montar). Treinador
        # externo segue sempre (preenche o buraco que o treinador deixou).
        if (
            not runner.external_coach
            and existing is not None
            and existing.kind in _RUNNING_KINDS
            and existing.origin != "oneoff"
        ):

            return (
                f"Você já tem *{existing.workout_type}* na "
                f"{weekday_label(target_day)} 😉 Se quiser que eu troque ou "
                "alivie, é só pedir."
            )

        history = await LoadTrainingHistory.execute(profile=profile)

        portrait = build_portrait(runner, history)

        # a curva semana a semana: pelo cérebro ela já vem no athlete_context;
        # no caminho determinístico (sem contexto) entra aqui
        if "EVOLUÇÃO SEMANA A SEMANA" not in (athlete_context or ""):

            evolution = WeeklyEvolutionDigest.for_profile(profile)

            if evolution:

                portrait = f"{portrait}\n{evolution}"

        if "BALANÇO DE ESTÍMULOS" not in (athlete_context or ""):

            stimulus = StimulusLedger.for_profile(profile)

            if stimulus:

                portrait = f"{portrait}\n{stimulus}"

        week_context = ExecutedWeekSummary.build(
            plan, history.activities, today
        ) or OneOffWorkoutFlow._plan_context(plan, target_day)

        target_label = f"{weekday_label(target_day)} ({target_date:%d/%m})"

        workout = await OneOffWorkoutEngine.build(
            runner=runner,
            objective=plan.objective or runner.goal,
            target_day=target_day,
            target_label=target_label,
            portrait=portrait,
            week_context=week_context,
            athlete_context=athlete_context,
            request=request,
            previous=OneOffWorkoutFlow._previous_text(
                plan, pending, target_date, existing,
            ),
        )

        # IA não produziu treino utilizável: deixa a conversa seguir (o chat
        # genérico responde — nunca silêncio)
        if workout is None:

            return None

        # o atleta JÁ pediu "monta e manda pro relógio": o pedido explícito é a
        # confirmação — grava e manda direto, sem o SIM duplo
        if commit_now:

            OneOffProposalStore.clear(profile)

            return await OneOffWorkoutFlow._commit_and_offer(
                profile, runner, target_date, workout.session,
                send_to_watch=True, intro=workout.message,
            )

        # CONFIRMAR ANTES DE ENTRAR: não grava agora — guarda a proposta e pede
        # o 'SIM'. Um 'não' descarta e NADA fica no plano/app (o atleta pediu
        # isso: o coach não deve criar treino sem confirmação). O relógio só é
        # oferecido DEPOIS que ele aceita. Ver [[project_treino_avulso]].
        OneOffProposalStore.set_pending(
            profile, workout.session, target_date, workout.message
        )

        return OneOffWorkoutFlow._compose_proposal(
            plan, workout, target_label
        )

    @staticmethod
    async def resolve_proposal_reply(
        profile: str,
        runner: RunnerProfile,
        incoming_text: str,
    ) -> str | None:
        """'SIM'/'não' à PROPOSTA de treino avulso (antes de entrar no plano).
        'sim' grava a sessão no plano e oferece o relógio; 'não' descarta e nada
        fica. Só age com proposta pendente; resposta ambígua devolve None (a
        conversa segue — o cérebro pode remontar)."""

        data = OneOffProposalStore.pending(profile)

        if data is None:

            return None

        norm = OneOffWorkoutDetector._normalize(incoming_text)

        if norm in _AFFIRMATIVE:

            return await OneOffWorkoutFlow.commit_pending(
                profile, runner,
                send_to_watch=OneOffWorkoutDetector.wants_watch(incoming_text),
            )

        if norm in _NEGATIVE:

            OneOffProposalStore.clear(profile)

            return (
                "Beleza, não adicionei nada. 👍 Qualquer hora é só pedir."
            )

        # resposta ambígua com proposta pendente: deixa a conversa seguir
        return None

    @staticmethod
    async def commit_pending(
        profile: str,
        runner: RunnerProfile,
        send_to_watch: bool = False,
    ) -> str | None:
        """Grava a proposta PENDENTE do avulso (o atleta aceitou — pelo 'sim'
        determinístico ou pelo cérebro lendo "beleza, pode colocar"). Com
        `send_to_watch` (ele já pediu o relógio), manda direto — sem a 2ª
        pergunta. None se não há proposta válida."""

        data = OneOffProposalStore.pending(profile)

        if data is None:

            return None

        OneOffProposalStore.clear(profile)

        return await OneOffWorkoutFlow._commit_and_offer(
            profile, runner, date.fromisoformat(data["date"]),
            data["session"], send_to_watch,
        )

    @staticmethod
    async def _commit_and_offer(
        profile: str,
        runner: RunnerProfile,
        target_date: date,
        session_dict: dict,
        send_to_watch: bool,
        intro: str = "",
    ) -> str:
        """Grava o avulso no plano e fecha: manda pro relógio (se pedido e
        conectado) ou oferece mandar."""

        target_day = WEEKDAYS[target_date.weekday()]

        plan, new_session = await OneOffWorkoutFlow._commit_session(
            profile, target_day, session_dict
        )

        if send_to_watch and GarminClient.is_connected(profile):

            single = replace(plan, sessions=[new_session])

            lines = "\n".join(
                WeeklyPlanMessageFormatter.session_lines(single)
            ).strip()

            watch = await OneOffWorkoutFlow._push_to_watch(
                profile, runner, target_date
            )

            head = f"{intro}\n\n" if intro else ""

            return (
                f"{head}✅ Adicionei teu treino de "
                f"{weekday_label(target_day)}:\n\n{lines}\n\n{watch}"
            )

        added = OneOffWorkoutFlow._compose_added(
            profile, plan, new_session, target_date, weekday_label(target_day),
        )

        return f"{intro}\n\n{added}" if intro else added

    @staticmethod
    async def resolve_watch_reply(
        profile: str,
        runner: RunnerProfile,
        incoming_text: str,
    ) -> str | None:
        """'SIM' (ou 'não') à oferta de mandar o treino avulso pro relógio.
        Empurra SÓ a sessão avulsa (push escopado), sem tocar no resto."""

        target_date = OneOffOfferStore.pending_date(profile)

        if target_date is None:

            return None

        norm = OneOffWorkoutDetector._normalize(incoming_text)

        if norm in _AFFIRMATIVE:

            OneOffOfferStore.clear(profile)

            return await OneOffWorkoutFlow._push_to_watch(
                profile, runner, target_date
            )

        if norm in _NEGATIVE:

            OneOffOfferStore.clear(profile)

            return (
                "Beleza! O treino tá aqui na conversa quando você quiser. 👍"
            )

        # resposta ambígua com oferta pendente: deixa a conversa seguir
        return None

    @staticmethod
    async def _push_to_watch(
        profile: str,
        runner: RunnerProfile,
        target_date: date,
    ) -> str:

        try:

            result = await push_one_off(profile, target_date)

        except Exception as e:

            print(f"Falha ao mandar treino avulso pro Garmin de "
                  f"'{profile}': {e}")

            result = {"ok": False}

        if not result.get("ok"):

            return (
                "Tentei mandar pro seu Garmin mas deu um problema agora 😕 "
                "Me chama daqui a pouco que eu tento de novo."
            )

        return (
            f"Pronto, {runner.name}! ⌚ Mandei o treino de "
            f"{target_date:%d/%m} pro seu Garmin. É só sincronizar o relógio "
            "com o app que ele aparece em Treino → Treinos. 🏃"
        )

    @staticmethod
    async def _commit_session(
        profile: str,
        target_day: str,
        session_dict: dict,
    ) -> tuple[TrainingPlan, PlannedSession]:
        """Grava DE VERDADE a sessão avulsa no plano (no 'sim' do atleta):
        recarrega o plano vivo, substitui o dia se já havia algo, reidrata os
        steps e salva. Marca origin='oneoff' — não mexe no resto do plano nem
        no que o treinador deixou nos outros dias. Devolve (plano, sessão)."""

        _, plan = await CurrentPlanProvider.for_profile(profile)

        session_dict = dict(session_dict)

        session_dict["steps"] = parse_steps(session_dict.get("steps") or [])

        new_session = PlannedSession(**session_dict)

        plan.sessions = [
            s for s in plan.sessions if s.day != target_day
        ] + [new_session]

        if target_day not in plan.running_days:

            plan.running_days = plan.running_days + [target_day]

        WeeklyPlanRepository().save(profile, plan)

        return plan, new_session

    @staticmethod
    def _date_for_day(day: str | None, today: date) -> date | None:
        """Próxima ocorrência (hoje conta) do dia da semana ('Sunday')."""

        index = {name: idx for idx, name in WEEKDAYS.items()}.get(day or "")

        if index is None:

            return None

        return today + timedelta(days=(index - today.weekday()) % 7)

    @staticmethod
    def _previous_text(
        plan: TrainingPlan,
        pending: dict | None,
        target_date: date,
        existing: PlannedSession | None,
    ) -> str:
        """O avulso que JÁ foi montado pra esse dia (proposta pendente ou avulso
        já gravado): o motor precisa vê-lo pra tratar a mensagem como AJUSTE
        dele — e, se não der pra atender, dizer por quê — em vez de montar
        outro treino do zero. Vazio quando é pedido novo."""

        session = None

        if pending and pending.get("date") == target_date.isoformat():

            session = OneOffWorkoutFlow._hydrate(pending["session"])

        elif existing is not None and existing.origin == "oneoff":

            session = existing

        if session is None:

            return ""

        return "\n".join(
            WeeklyPlanMessageFormatter.session_lines(
                replace(plan, sessions=[session])
            )
        ).strip()

    @staticmethod
    def _hydrate(session_dict: dict) -> PlannedSession:
        """Sessão (dict) -> PlannedSession pra formatação, reidratando os steps.
        Não persiste nada — só pra montar o preview da proposta."""

        data = dict(session_dict)

        data["steps"] = parse_steps(data.get("steps") or [])

        return PlannedSession(**data)

    @staticmethod
    def _compose_proposal(
        plan: TrainingPlan,
        workout,
        target_label: str,
    ) -> str:
        """Preview da PROPOSTA (ainda não gravou): mostra o treino e pede o
        'SIM'. Um 'não' descarta. Reusa o formatador (plano de 1 sessão)."""

        single = replace(
            plan, sessions=[OneOffWorkoutFlow._hydrate(workout.session)]
        )

        lines = "\n".join(
            WeeklyPlanMessageFormatter.session_lines(single)
        ).strip()

        return (
            f"{workout.message}\n\n📋 {target_label}\n\n{lines}\n\n"
            "👉 Quer que eu adicione ao teu plano? Responde *SIM* que eu "
            "coloco (aí depois te ofereço mandar pro relógio). Se não quiser, "
            "é só falar."
        )

    @staticmethod
    def _compose_added(
        profile: str,
        plan: TrainingPlan,
        new_session: PlannedSession,
        target_date: date,
        day_label: str,
    ) -> str:
        """Confirmação pós-'SIM': o treino ENTROU no plano; oferece o relógio
        (push escopado do avulso, inclusive pra treinador externo)."""

        single = replace(plan, sessions=[new_session])

        lines = "\n".join(
            WeeklyPlanMessageFormatter.session_lines(single)
        ).strip()

        body = f"Prontinho, adicionei teu treino de {day_label}! ✅\n\n{lines}"

        if GarminClient.is_connected(profile):

            OneOffOfferStore.set_pending(profile, target_date)

            body += (
                "\n\n⌚ Quer esse treino no seu relógio? "
                "Responde *SIM* que eu mando."
            )

        return body

    @staticmethod
    def _plan_context(plan: TrainingPlan, target_day: str) -> str:
        """Fallback de contexto quando não há execução ainda: só lista o que o
        plano já tem nos outros dias da semana."""

        lines = []

        for session in plan.sessions:

            if session.day == target_day:

                continue

            distance = (
                f"{session.planned_distance_km:.0f}km"
                if session.planned_distance_km
                else "s/ distância"
            )

            lines.append(
                f"- {weekday_label(session.day)}: "
                f"{session.workout_type}, {distance}"
            )

        return "\n".join(lines) or "(semana ainda sem treinos registrados)"
