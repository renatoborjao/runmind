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
    ) -> str | None:

        if not OneOffWorkoutDetector.looks_like_request(incoming_text):

            return None

        return await OneOffWorkoutFlow.build_for(profile, runner, incoming_text)

    @staticmethod
    async def build_for(
        profile: str,
        runner: RunnerProfile,
        incoming_text: str,
        athlete_context: str = "",
    ) -> str | None:
        """Núcleo SEM o portão de palavra-chave: resolve o dia, monta a sessão
        avulsa ancorada no histórico + estado atual do atleta e oferece o
        relógio. Usado pelo cérebro do coach (que já reconheceu o pedido) e pelo
        handle() determinístico (fallback). Ver [[project_roteador_acao_ia]]."""

        today = today_local()

        target_date = OneOffWorkoutDetector.resolve_target_date(
            incoming_text, today
        )

        if target_date is None:

            return (
                "Boa! Pra qual dia você quer o treino? "
                "(ex.: 'domingo', 'amanhã', '02/08') 🗓️"
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
        # já tem (se quiser mudar, é negociação/aversão). Treinador externo
        # segue sempre (preenche o buraco que o treinador deixou).
        if (
            not runner.external_coach
            and existing is not None
            and existing.kind in _RUNNING_KINDS
        ):

            return (
                f"Você já tem *{existing.workout_type}* na "
                f"{weekday_label(target_day)} 😉 Se quiser que eu troque ou "
                "alivie, é só pedir."
            )

        history = await LoadTrainingHistory.execute(profile=profile)

        portrait = build_portrait(runner, history)

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
        )

        # IA não produziu treino utilizável: deixa a conversa seguir (o chat
        # genérico responde — nunca silêncio)
        if workout is None:

            return None

        new_session = OneOffWorkoutFlow._save_session(
            profile, plan, target_day, workout
        )

        return OneOffWorkoutFlow._compose_reply(
            profile, plan, new_session, target_date, target_label,
            workout.message,
        )

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
    def _save_session(
        profile: str,
        plan: TrainingPlan,
        target_day: str,
        workout,
    ) -> PlannedSession:
        """Grava a sessão avulsa no plano da semana (substitui o dia se já
        havia algo), reidratando os steps. Marca origin='oneoff' — não mexe
        no resto do plano nem no que o treinador deixou nos outros dias."""

        session_dict = dict(workout.session)

        session_dict["steps"] = parse_steps(session_dict.get("steps") or [])

        new_session = PlannedSession(**session_dict)

        plan.sessions = [
            s for s in plan.sessions if s.day != target_day
        ] + [new_session]

        if target_day not in plan.running_days:

            plan.running_days = plan.running_days + [target_day]

        WeeklyPlanRepository().save(profile, plan)

        return new_session

    @staticmethod
    def _compose_reply(
        profile: str,
        plan: TrainingPlan,
        new_session: PlannedSession,
        target_date: date,
        target_label: str,
        intro: str,
    ) -> str:

        # formata só a sessão avulsa, reusando o formatador (plano de 1 sessão)
        single = replace(plan, sessions=[new_session])

        lines = "\n".join(
            WeeklyPlanMessageFormatter.session_lines(single)
        ).strip()

        body = f"{intro}\n\n📋 {target_label}\n\n{lines}"

        # oferece o relógio (inclusive treinador externo — o avulso é NOSSO)
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
