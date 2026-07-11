import re
import unicodedata

from app.application.coach.planning.aversion_swap_engine import (
    AversionSwapEngine,
)
from app.application.planner.current_plan_provider import CurrentPlanProvider
from app.core.clock import now_local
from app.domain.entities.plan_proposal import PlanProposal
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.persistence.plan_proposal_repository import (
    PlanProposalRepository,
)

# portão determinístico BARATO: só chama a IA se a mensagem cheira a
# pedido de troca/aversão (evita 1 chamada Gemini em toda mensagem).
_TYPE_WORDS = [
    "tiro", "tiros", "longao", "long run", "rodagem", "fartlek", "tempo",
    "intervalado", "intervalo", "subida", "subidas", "ladeira",
    "regenerativo", "velocidade", "progressivo", "trote", "treino",
]

_CHANGE_CUES = [
    "nao gosto", "nao curto", "odeio", "detesto", "enjoei", "enjoado",
    "cansei", "cansado de", "saco", "chato", "chata", "prefiro nao",
    "nao quero", "troca", "trocar", "muda", "mudar", "tira", "tirar",
    "evitar", "evita", "nao aguento", "sem ", "menos",
]


class AversionFlow:
    """Fluxo reativo da aversão: o atleta reclama de um tipo de treino no
    chat, o coach PROPÕE uma troca (mantendo o estímulo) e guarda a proposta
    pendente pro 'sim'. Não aplica nada sozinho."""

    @staticmethod
    async def handle(
        profile: str,
        runner: RunnerProfile,
        incoming_text: str,
    ) -> str | None:
        """Devolve o preview da proposta (mensagem pro atleta) se detectou e
        montou uma troca; None caso contrário (a conversa segue normal)."""

        # treinador humano: RunMind só acompanha o plano dele, não mexe
        if runner.external_coach:

            return None

        if not AversionFlow._looks_like_aversion(incoming_text):

            return None

        _, plan = await CurrentPlanProvider.for_profile(profile)

        if not plan.sessions or plan.source == "externo":

            return None

        swap = await AversionSwapEngine.propose(runner, plan, incoming_text)

        # a IA concluiu que não era um pedido de troca claro
        if swap is None:

            return None

        proposal = PlanProposal(
            kind="aversion",
            week_start=plan.week_start.isoformat(),
            preview=swap.message,
            created_at=now_local().isoformat(),
            operations=[
                {"action": "replace", "day": swap.day, "session": swap.session},
            ],
        )

        PlanProposalRepository().save(profile, proposal)

        return swap.message

    @staticmethod
    def _looks_like_aversion(text: str) -> bool:

        norm = AversionFlow._normalize(text)

        has_type = any(word in norm for word in _TYPE_WORDS)

        has_cue = any(cue in norm for cue in _CHANGE_CUES)

        return has_type and has_cue

    @staticmethod
    def _normalize(text: str) -> str:

        lowered = text.lower().strip()

        without_accents = "".join(
            char
            for char in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(char) != "Mn"
        )

        return re.sub(r"\s+", " ", without_accents)
