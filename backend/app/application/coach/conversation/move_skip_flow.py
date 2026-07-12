import re
import unicodedata
from dataclasses import asdict

from app.application.coach.planning.move_skip_engine import MoveSkipEngine
from app.application.planner.current_plan_provider import CurrentPlanProvider
from app.core.clock import now_local, today_local
from app.domain.entities.plan_proposal import PlanProposal
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.persistence.plan_proposal_repository import (
    PlanProposalRepository,
)

# portão barato: só chama a IA se a mensagem cheira a mover/pular treino
_MOVE_CUES = [
    "joga", "jogar", "passa o", "passa pra", "passar o", "move o", "mover",
    "no lugar de", "em vez de", "adia", "adiar", "remarca", "remarcar",
    "antecipa", "antecipar", "troca o dia", "troca pra", "trocar de dia",
    "empurra o treino", "empurrar o treino", "faco quarta", "corro quarta",
]

_SKIP_CUES = [
    "nao vou treinar", "nao vou correr", "nao vou fazer o treino",
    "pula o treino", "pular o treino", "pula hoje", "pular hoje",
    "nao consigo treinar", "nao treino hoje", "sem treino hoje",
    "nao da pra treinar", "vou faltar", "nao vou conseguir treinar",
    "cancela o treino", "nao rola treinar",
]

_RUNNING_KINDS = {"run", "walk", "run_walk"}


class MoveSkipFlow:
    """Fluxo reativo de mover/pular treino: o atleta pede no chat ("joga pra
    quarta" / "não vou treinar hoje"), o coach PROPÕE a mudança e guarda a
    proposta pendente pro 'sim'. Não aplica nada sozinho."""

    @staticmethod
    async def handle(
        profile: str,
        runner: RunnerProfile,
        incoming_text: str,
    ) -> str | None:

        # treinador humano: RunMind não reestrutura o plano dele
        if runner.external_coach:

            return None

        if not MoveSkipFlow._looks_like_move_or_skip(incoming_text):

            return None

        _, plan = await CurrentPlanProvider.for_profile(profile)

        if not plan.sessions or plan.source == "externo":

            return None

        request = await MoveSkipEngine.propose(
            runner, plan, incoming_text, today_local()
        )

        if request is None:

            return None

        operations = MoveSkipFlow._operations(plan, request)

        if not operations:

            return None

        PlanProposalRepository().save(
            profile,
            PlanProposal(
                kind=request.action,
                week_start=plan.week_start.isoformat(),
                preview=request.message,
                created_at=now_local().isoformat(),
                operations=operations,
            ),
        )

        return request.message

    @staticmethod
    def _operations(
        plan: TrainingPlan,
        request,
    ) -> list[dict]:

        if request.action == "skip":

            return [{"action": "drop", "day": request.day}]

        # move: tira do dia de origem e põe a MESMA sessão no destino
        source = plan.find_session_by_day(request.day)

        if source is None:

            return []

        session = asdict(source)

        session["day"] = request.target_day

        session.pop("garmin", None)   # sessão movida nasce sem registro Garmin

        return [
            {"action": "drop", "day": request.day},
            {
                "action": "replace",
                "day": request.target_day,
                "session": session,
            },
        ]

    @staticmethod
    def _looks_like_move_or_skip(text: str) -> bool:

        norm = MoveSkipFlow._normalize(text)

        return any(cue in norm for cue in _MOVE_CUES + _SKIP_CUES)

    @staticmethod
    def _normalize(text: str) -> str:

        lowered = text.lower().strip()

        without_accents = "".join(
            char
            for char in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(char) != "Mn"
        )

        return re.sub(r"\s+", " ", without_accents)
