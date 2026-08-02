from app.application.coach.conversation.goal_change_detector import (
    GoalChangeDetector,
)
from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)
from app.application.garmin.plan_watch_sync import resync_watch_if_pushed
from app.application.onboarding.onboarding_answer_parser import (
    OnboardingAnswerParser,
)
from app.application.planner.current_plan_provider import CurrentPlanProvider
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.persistence.pending_goal_repository import (
    PendingGoalRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

# Pergunta determinística quando o atleta quer trocar a meta mas ainda não
# disse qual — evita depender do chat genérico adivinhar, e arma o estado
# pendente pra ler a resposta seguinte como o objetivo novo.
_ASK_WHICH_GOAL = (
    "Bora ajustar! 🎯 Qual é o objetivo agora — outra distância, outro "
    "tempo-alvo, ou algo tipo saúde/evoluir sem prova marcada? Se tiver "
    "data de prova, me conta também que eu já monto o caminho."
)


class GoalChangeApplier:
    """Fluxo reativo de troca de OBJETIVO: o atleta pede pra mudar a meta
    no chat (texto livre, com ou sem prova/data/tempo-alvo).

    Duas cabeças:
    - COM cronograma (data de prova OU tempo-alvo): é uma meta concreta com
      prazo — atualiza tudo e regera a semana pra bater o caminho.
    - SEM cronograma (aspiração tipo "quero correr 21km, com saúde"): registra
      a meta e a memória, mas NÃO vira a semana de cabeça pra baixo — a
      progressão semanal leva o volume pra lá aos poucos ('progride devagar').

    Estado: quando o atleta quer trocar mas ainda não disse qual, o coach
    pergunta e arma um pendente; a resposta seguinte cai aqui mesmo (sem
    precisar repetir a palavra-gatilho), em vez de escorregar pra negociação."""

    @staticmethod
    async def handle(
        profile: str,
        runner: RunnerProfile,
        incoming_text: str,
    ) -> str | None:

        pending_repo = PendingGoalRepository()

        pending = pending_repo.is_pending(profile)

        # sem pendente e sem cheiro de troca de meta: não é comigo
        if not pending and not GoalChangeDetector.looks_like_goal_change(
            incoming_text
        ):

            return None

        extracted = await OnboardingAnswerParser.parse(
            step="ASK_GOAL",
            question="Qual é o objetivo agora?",
            answer=incoming_text,
        )

        goal = str(extracted.get("goal") or "").strip()

        if not goal:

            # estávamos esperando a meta e a resposta não trouxe uma —
            # solta o estado e deixa o fluxo normal seguir
            if pending:

                pending_repo.clear(profile)

                return None

            # pedido CLARO de trocar mas sem dizer pra quê — arma o estado e
            # pergunta; a resposta seguinte cai aqui como a meta nova
            if GoalChangeDetector.is_explicit_change_request(incoming_text):

                pending_repo.mark(profile)

                return _ASK_WHICH_GOAL

            # falso-positivo do portão barato (sem intenção clara de troca):
            # não pergunta nada, deixa o chat responder normalmente
            return None

        # temos um objetivo de verdade: consome o estado pendente
        pending_repo.clear(profile)

        # ---- aspiração (sem data e sem tempo-alvo): registra e progride ----
        if not (extracted.get("race_date") or extracted.get("target_time")):

            return await GoalChangeApplier._register_aspiration(
                profile,
                runner,
                goal,
            )

        # ---- meta concreta (tem prazo/tempo): atualiza e regera o caminho --
        return await GoalChangeApplier._apply_concrete_goal(
            profile,
            runner,
            goal,
            extracted,
        )

    @staticmethod
    async def _register_aspiration(
        profile: str,
        runner: RunnerProfile,
        goal: str,
    ) -> str:
        """Meta sem data: anota o objetivo e a aspiração de longo prazo, mas
        mantém a semana atual. A progressão semanal puxa o volume gradualmente
        com a meta nova já registrada — sem plano agressivo do nada."""

        RunnerProfileRepository().update_fields(profile, {"goal": goal})

        RunnerMemoryService.process(
            profile,
            {
                "add": [
                    {
                        "category": "objetivo",
                        "content": (
                            f"Meta de longo prazo: {goal} — sem data "
                            "definida, prioridade saúde e progressão gradual."
                        ),
                    }
                ]
            },
        )

        if runner.external_coach:

            return f"Anotado! Atualizei seu objetivo pra: {goal}. 🎯"

        return (
            f"Anotado, {runner.name}! Nova meta: {goal}. 🎯 Não vou virar "
            "sua semana de cabeça pra baixo — como não tem data marcada, "
            "vou te levando pra lá com saúde, aumentando aos poucos semana a "
            "semana. Sua semana atual segue como está. Quando definir uma "
            "data de prova, é só falar que eu monto o caminho completo. 👊"
        )

    @staticmethod
    async def _apply_concrete_goal(
        profile: str,
        runner: RunnerProfile,
        goal: str,
        extracted: dict,
    ) -> str:
        """Meta com prazo/tempo-alvo: atualiza o perfil e regera a semana já
        na meta nova (o caminho passa a mirar a prova)."""

        updates = {"goal": goal}

        # prova/data/tempo só entram se vieram citados — não apaga o que já
        # estava registrado (mesmo padrão de RunnerMemoryService._sync_race)
        if extracted.get("target_race"):

            updates["target_race"] = extracted["target_race"]

        if extracted.get("target_time"):

            updates["target_time"] = extracted["target_time"]

        if extracted.get("race_date"):

            updates["race_date"] = extracted["race_date"]

        RunnerProfileRepository().update_fields(profile, updates)

        # treinador humano: RunMind só acompanha o plano dele, não gera
        if runner.external_coach:

            return f"Anotado! Atualizei seu objetivo pra: {goal}. 🎯"

        _, plan = await CurrentPlanProvider.for_profile(
            profile,
            force=True,
        )

        # plano REGERADO pra meta nova: mantém o relógio em sincronia (só pra
        # quem já sincronizou; best-effort)
        synced = await resync_watch_if_pushed(profile, plan)

        plan_text = WeeklyPlanMessageFormatter.week_plan_message(
            runner.name,
            plan,
        )

        watch_note = (
            "\n\n⌚ Já atualizei os treinos no seu relógio também."
            if synced
            else ""
        )

        return (
            f"Fechou, {runner.name}! Atualizei seu objetivo pra: {goal}. 🎯 "
            f"Já ajustei o plano da semana pra essa meta nova.\n\n{plan_text}"
            f"{watch_note}"
        )
