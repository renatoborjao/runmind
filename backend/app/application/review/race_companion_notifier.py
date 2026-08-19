"""Companheiro de prova: os toques PROATIVOS ancorados na data da prova. Um
coach de verdade conduz o atleta pela reta final — explica o polimento, relembra
a estratégia, acalma na véspera e manda energia na manhã da prova.

Roda de hora em hora; cada atleta é avaliado no horário local, e cada toque sai
UMA vez (dedup por prova+toque). Silencioso quando não há prova marcada ou o dia
não bate um marco. Ver [[project_ideias_produto]]."""

from app.application.coach.planning.race_strategy_engine import (
    RaceStrategyEngine,
)
from app.application.history.metrics_resolver import MetricsResolver
from app.application.notifications.coach_outbox import CoachOutbox
from app.application.planner.pace_formatter import PaceFormatter
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import now_in, today_local, use_athlete_timezone
from app.domain.entities.training_goal import TrainingGoal
from app.infrastructure.persistence.dispatch_guard import DispatchGuard
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# hora local em que os toques de prova saem (manhã calma; a manhã da prova
# idealmente cedo — v1 usa a mesma hora, best-effort)
RACE_HOUR = 7

# marcos (dias que faltam) -> id do toque. Ordem do mais próximo ao mais longe:
# escolhemos o marco de menor limiar que ainda é >= dias que faltam (assim, se
# um atleta cadastra a prova em cima da hora, pega o toque certo, não o de 2 sem)
_TOUCHPOINTS = [
    (0, "race_day"),
    (1, "eve"),
    (3, "journey"),
    (7, "race_week"),
    (14, "taper"),
]

_KIND = "race_companion"


class RaceCompanionNotifier:

    @staticmethod
    async def notify_all() -> None:

        for profile in RunnerProfileRepository().list_all():

            try:

                await RaceCompanionNotifier._notify_one(profile)

            except Exception as e:

                print(f"Companheiro de prova falhou para '{profile}': {e}")

    @staticmethod
    async def _notify_one(profile: str) -> None:

        runner = LoadRunnerProfile.execute(profile)

        use_athlete_timezone(runner.timezone)

        local = now_in(runner.timezone)

        if local.hour != RACE_HOUR:

            return

        goal = BuildTrainingGoal.execute(runner)

        if goal.race_date is None:

            return

        days_until = (goal.race_date - today_local()).days

        touch = RaceCompanionNotifier._touchpoint(profile, days_until, goal)

        if touch is None:

            return

        message = await RaceCompanionNotifier._message(profile, runner, goal, touch)

        if message is None:

            return

        # dia da prova, véspera e jornada são os toques EMOCIONAIS: saem em
        # texto + áudio (arrancada na voz do coach). Semana/polimento só texto.
        emotional = touch in ("race_day", "eve", "journey")

        # kind pro governador: dia/véspera/jornada são ESSENCIAIS (emocionais,
        # sempre saem); semana/polimento são EXTRAS informativos (cedem no cheio)
        kind = {
            "race_day": "race_day",
            "eve": "race_eve",
            "journey": "race_journey",
            "race_week": "race_week",
            "taper": "race_taper",
        }.get(touch, "race_week")

        await CoachOutbox.send(
            runner, message, voice=emotional, profile=profile, kind=kind,
        )

        DispatchGuard.mark(
            _KIND, profile, f"{goal.race_date.isoformat()}:{touch}"
        )

    @staticmethod
    def _touchpoint(profile: str, days_until: int, goal: TrainingGoal) -> str | None:
        """O marco de HOJE: o BRACKET em que o atleta está — o de MENOR limiar
        que ainda comporta os dias que faltam. Dispara só se ainda não saiu; se
        JÁ saiu, para aqui (None) — NUNCA cai pro marco seguinte, mais distante
        e fora de hora. Era o bug do Renato: com a 'semana da prova' já enviada,
        a 4 dias da prova ele caía no 'polimento' (que é de ~2 semanas antes).
        Prova no passado -> None."""

        if days_until < 0:

            return None

        race = goal.race_date.isoformat()

        # _TOUCHPOINTS vai do menor limiar (0) pro maior (14): o PRIMEIRO que
        # comporta os dias que faltam é o bracket de hoje — e o único candidato.
        for threshold, touch in _TOUCHPOINTS:

            if days_until <= threshold:

                if DispatchGuard.already_sent(_KIND, profile, f"{race}:{touch}"):

                    return None

                return touch

        return None

    @staticmethod
    async def _message(
        profile: str,
        runner,
        goal: TrainingGoal,
        touch: str,
    ) -> str | None:

        # a PROVA pela distância (10k), NUNCA o goal.name (aspiração de fundo
        # tipo "correr 21 km, buscar saúde..."), que trocava a prova pela meta
        # e fazia o coach dizer "polimento pra 21km" na prova de 10k.
        race = goal.race_label

        if touch == "taper":

            # taper: só pra atleta cujo plano é NOSSO (nós reduzimos o volume);
            # de treinador externo, o polimento é conduzido pelo treinador dele
            if runner.external_coach:

                return None

            return (
                f"Você entrou na reta de *polimento* pra sua prova de {race} 🎯\n\n"
                "A partir de agora eu reduzo o volume DE PROPÓSITO — o corpo "
                "consolida todo o trabalho das últimas semanas. Se as pernas "
                "coçarem pra correr mais, ótimo sinal: é energia sendo guardada "
                "pro dia. Menos é mais agora. Confia no processo. 💪"
            )

        # jornada até a prova (3 dias antes): o retrospecto emocional "olha o
        # caminho que você fez". Conteúdo próprio (não usa a linha de pace).
        if touch == "journey":

            return await RaceCompanionNotifier._journey_message(
                profile, runner, goal,
            )

        pace_line = await RaceCompanionNotifier._pace_line(profile, runner, goal)

        if touch == "race_week":

            extra = f"\n\n{pace_line}" if pace_line else ""

            base = (
                f"É a *semana da sua prova*! 🔥 Sua prova de {race} tá logo ali.\n\n"
                "Semana de afiar, não de ganhar forma — o trabalho pesado já "
                "foi feito. Foco em dormir bem, comer direito e chegar leve."
                f"{extra}\n\n"
                "Quer revisar a estratégia completa? Manda 'como corro a prova'."
            )

            # oferta proativa: mandar a prova como treino guiado pro relógio.
            # Arma o pendente pra o "sim" empurrar (só quem dá pra empurrar).
            from app.application.coach.conversation.race_workout_flow import (
                RaceWorkoutFlow,
            )
            from app.infrastructure.integrations.garmin.race_workout_offer_store import (  # noqa: E501
                RaceWorkoutOfferStore,
            )

            if RaceWorkoutFlow.eligible(
                profile, runner, goal.race_date.isoformat()
            ):

                RaceWorkoutOfferStore.set_pending(profile)

                base += RaceWorkoutFlow.offer_text()

            return base

        if touch == "eve":

            extra = f"\n\n{pace_line}" if pace_line else ""

            return (
                f"Amanhã é o *dia*! 🙌 Reta final pra sua prova de {race}.\n\n"
                "Hoje: hidrate bem desde já, coma o que seu corpo conhece "
                "(nada novo!), separe roupa/tênis/número à noite e durma o que "
                "der — a noite que mais conta é a de 2 dias atrás, então relaxa "
                "se o sono não vier. O trabalho já foi feito; amanhã é colher."
                f"{extra}"
            )

        # race_day
        extra = f"\n\n{pace_line}" if pace_line else ""

        return (
            f"É HOJE! 🏁 Sua prova de {race} chegou.\n\n"
            "Confia no plano: largada CONTROLADA, segura na primeira metade e "
            "vai buscar na segunda. Você treinou pra isso — agora é só correr "
            f"o que já é seu.{extra}\n\nBoa prova! Vai com tudo. 🚀"
        )

    @staticmethod
    async def _journey_message(profile: str, runner, goal: TrainingGoal) -> str | None:
        """A recap da JORNADA até a prova (retrospecto emocional). Best-effort:
        sem histórico/sem dá pra montar, volta None (o toque não sai)."""

        try:

            from app.application.review.race_journey_builder import (
                RaceJourneyBuilder,
            )
            from app.application.review.race_journey_message_formatter import (
                RaceJourneyMessageFormatter,
            )

            history = await LoadTrainingHistory.execute(profile=profile)

            journey = RaceJourneyBuilder.build(runner, history, goal)

            if journey is None:

                return None

            return RaceJourneyMessageFormatter.format(runner.name, journey)

        except Exception as e:

            print(f"Recap da jornada falhou p/ '{profile}': {e}")

            return None

    @staticmethod
    async def _pace_line(profile: str, runner, goal: TrainingGoal) -> str | None:
        """Uma linha compacta com o pace-alvo, pra emendar nos toques. Best-
        effort: sem forma/tempo, volta None (o toque vai sem a linha)."""

        try:

            history = await LoadTrainingHistory.execute(profile=profile)

            metrics = MetricsResolver.resolve(runner, history)

            plan = RaceStrategyEngine.plan(goal, metrics)

            if plan is None:

                return None

            avg = PaceFormatter.format(plan.avg_pace_min)

            return f"🎯 Lembrete: pace-alvo ~{avg}/km, largada controlada."

        except Exception as e:

            print(f"Linha de pace do companheiro falhou p/ '{profile}': {e}")

            return None
