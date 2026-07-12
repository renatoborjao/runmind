import copy
import re
import unicodedata

from app.application.coach.conversation.plan_change_applier import (
    PlanChangeApplier,
)
from app.application.coach.planning.negotiation_engine import NegotiationEngine
from app.application.planner.current_plan_provider import CurrentPlanProvider
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.core.clock import now_local
from app.domain.entities.plan_proposal import PlanProposal
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.persistence.plan_proposal_repository import (
    PlanProposalRepository,
)

# portão determinístico BARATO: só chama a IA se a mensagem cheira a pedido de
# AJUSTE de carga/volume/plano (o que aversão-de-tipo e mover/pular NÃO pegam).
# Falso positivo só custa 1 chamada (a IA devolve adjust:false e cai no chat).
_LOAD_WORDS = [
    "leve", "leves", "pesado", "pesada", "puxado", "puxada", "forte", "fortes",
    "tranquilo", "tranquila", "facil", "dificil", "volume", "km", "quilometr",
    "intensidade", "carga", "cansativ", "plano", "semana", "rodagem",
    "rodagens", "distancia", "treininho", "corridinha",
]

_ADJUST_CUES = [
    "mais", "menos", "aumenta", "aumentar", "diminui", "diminuir", "reduz",
    "reduzir", "deixa", "muda", "mudar", "ajusta", "ajustar", "alivia",
    "aliviar", "pega leve", "demais", "de mais", "queria", "quero", "poderia",
    "da pra", "consegue", "acho que", "ta muito", "esta muito", "to achando",
    "suave", "encaixa", "encaixar",
]


class NegotiationFlow:
    """Fluxo reativo da NEGOCIAÇÃO geral: o atleta pede pra ajustar a carga/
    volume/composição da semana no chat, o coach remonta a semana MALEÁVEL MAS
    COM CRITÉRIO (segura o essencial da meta), mostra a semana revisada e guarda
    a proposta pendente pro 'sim'. Não aplica nada sozinho."""

    @staticmethod
    async def handle(
        profile: str,
        runner: RunnerProfile,
        incoming_text: str,
    ) -> str | None:

        # treinador humano: RunMind só acompanha, não remonta o plano dele
        if runner.external_coach:

            return None

        if not NegotiationFlow._looks_like_negotiation(incoming_text):

            return None

        _, plan = await CurrentPlanProvider.for_profile(profile)

        if not plan.sessions or plan.source == "externo":

            return None

        negotiation = await NegotiationEngine.propose(
            runner,
            plan,
            incoming_text,
        )

        # a IA concluiu que não era um pedido de ajuste claro
        if negotiation is None:

            return None

        # mostra a semana JÁ revisada (aplica as ops numa cópia) + pede o 'sim'
        preview_plan = copy.deepcopy(plan)

        PlanChangeApplier._apply_operations(
            preview_plan,
            negotiation.operations,
        )

        revised = "\n".join(
            WeeklyPlanMessageFormatter.session_lines(preview_plan)
        ).strip()

        message = (
            f"{negotiation.message}\n\n"
            f"📋 Como fica sua semana:\n\n{revised}\n\n"
            "Posso aplicar? (responde *sim* ou *não*)"
        )

        proposal = PlanProposal(
            kind="negotiation",
            week_start=plan.week_start.isoformat(),
            preview=message,
            created_at=now_local().isoformat(),
            operations=negotiation.operations,
        )

        PlanProposalRepository().save(profile, proposal)

        return message

    @staticmethod
    def _looks_like_negotiation(text: str) -> bool:

        norm = NegotiationFlow._normalize(text)

        has_load = any(word in norm for word in _LOAD_WORDS)

        has_cue = any(cue in norm for cue in _ADJUST_CUES)

        return has_load and has_cue

    @staticmethod
    def _normalize(text: str) -> str:

        lowered = text.lower().strip()

        without_accents = "".join(
            char
            for char in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(char) != "Mn"
        )

        return re.sub(r"\s+", " ", without_accents)
