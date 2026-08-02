import re
import unicodedata
from datetime import date

from app.application.coach.memory.runner_memory_service import (
    RunnerMemoryService,
)
from app.application.coach.planning.training_preference_engine import (
    TrainingPreferenceEngine,
)
from app.core.weekdays import weekday_label
from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.persistence.conversation_repository import (
    ConversationRepository,
)
from app.infrastructure.persistence.plan_proposal_repository import (
    PlanProposalRepository,
)
from app.infrastructure.persistence.runner_memory_repository import (
    RunnerMemoryRepository,
)

# turnos recentes de contexto pro engine (barato, leitura de arquivo)
CONTEXT_TURNS = 6

# portão determinístico BARATO: a mensagem cheira a preferência de FORMA da
# rotina (shape) E tem sinal de DURABILIDADE/horizonte (pra frente, não só esta
# semana). Só aí gasta 1 chamada de IA — falso positivo cai de volta nos outros
# fluxos (o engine devolve None). Sem o sinal durável, "deixa a semana leve"
# (ajuste desta semana) NÃO entra aqui: segue pro NegotiationFlow, como antes.
_SHAPE = [
    "treino", "semana", "minuto", "tempo", "horario", "rotina", "agenda",
    "sem pressa", "fim de semana", "cabe", "caber", "encaixa", "corrido",
]

_DURABILITY = [
    "a partir", "de agora", "daqui pra", "daqui para", "sempre", "no geral",
    "toda semana", "todas as semanas", "durante a semana", "dia de semana",
    "dias de semana", "semana que vem", "proxima semana", "costumo",
    "normalmente", "geralmente", "tende a", "de praxe", "por padrao",
    "manter", "mantem", "mantenha", "de segunda a",
]


class TrainingPreferenceFlow:
    """Preferência DURÁVEL de rotina ("treinos de semana em até 50 min, a
    partir da próxima"): o coach ENTENDE, grava na memória evolutiva (que já
    alimenta a geração do plano) e confirma — sem mexer na semana atual (que
    pode já ter fechado). Roda ANTES da negociação geral, pra um pedido pra
    frente não virar uma proposta de mexer na semana de agora. Ver
    [[project_pendencias_abertas]] e o valor 'tudo é dinâmico'."""

    @staticmethod
    async def handle(
        profile: str,
        runner: RunnerProfile,
        incoming_text: str,
    ) -> str | None:

        if not TrainingPreferenceFlow._looks_like(incoming_text):

            return None

        current_memories = RunnerMemoryRepository().active(profile)

        recent_turns = ConversationRepository().recent_turns(profile)

        preference = await TrainingPreferenceEngine.extract(
            runner_name=runner.name,
            current_memories=current_memories,
            recent_turns=recent_turns[-CONTEXT_TURNS:],
            incoming_text=incoming_text,
            # atleta de treinador humano: guardamos a preferência mesmo assim
            # (memória é dinâmica), mas a confirmação não promete montar plano
            plan_owned=not runner.external_coach,
            # pilares do onboarding: a preferência COMPLEMENTA, não redefine os
            # dias fixos nem sabota a meta
            training_days=TrainingPreferenceFlow._training_days(runner),
            objective=TrainingPreferenceFlow._objective(runner),
        )

        # a IA concluiu que não é preferência durável (é ajuste desta semana,
        # pergunta, desabafo): deixa o turno seguir pros outros fluxos
        if preference is None:

            return None

        # grava no MESMO trilho da memória evolutiva — vira dado dinâmico que a
        # geração do plano lê ("Memória do atleta"), não campo rígido
        RunnerMemoryService.process(
            profile,
            {
                "add": [
                    {
                        "category": preference.category,
                        "content": preference.content,
                    }
                ],
                "archive": preference.archive,
            },
        )

        # o atleta redirecionou o RUMO do plano: uma proposta desta semana que
        # tenha ficado pendente perdeu o contexto — descarta pra o próximo "sim"
        # não aplicar algo que ele já superou
        PlanProposalRepository().clear(profile)

        return preference.reply

    @staticmethod
    def _training_days(runner: RunnerProfile) -> str:
        """Dias de treino do onboarding em pt-BR — os dias FIXOS que a
        preferência complementa, nunca redefine."""

        return ", ".join(
            weekday_label(day) for day in runner.preferred_running_days
        )

    @staticmethod
    def _objective(runner: RunnerProfile) -> str:
        """Meta do atleta pra ancorar a preferência — o teto de tempo/ritmo
        não pode furar o essencial rumo ao objetivo. Junta a aspiração de
        fundo (goal) com a prova concreta (nome + data + tempo-alvo), pra o
        motor saber quando há prova PERTO a proteger."""

        objective = runner.goal or ""

        if runner.target_race:

            race = f"prova: {runner.target_race}"

            if runner.race_date:

                race = f"{race} em {TrainingPreferenceFlow._fmt_date(runner.race_date)}"

            if runner.target_time:

                race = f"{race} (meta {runner.target_time})"

            objective = f"{objective} — {race}".strip(" —")

        elif runner.target_time:

            objective = f"{objective} (meta {runner.target_time})".strip()

        return objective

    @staticmethod
    def _fmt_date(iso: str) -> str:
        """'2026-08-23' -> '23/08/2026'; se vier torto, devolve como está."""

        try:

            return date.fromisoformat(iso).strftime("%d/%m/%Y")

        except (ValueError, TypeError):

            return iso

    @staticmethod
    def _looks_like(text: str) -> bool:

        norm = TrainingPreferenceFlow._normalize(text)

        has_shape = any(word in norm for word in _SHAPE)

        has_durability = any(word in norm for word in _DURABILITY)

        return has_shape and has_durability

    @staticmethod
    def _normalize(text: str) -> str:

        lowered = text.lower().strip()

        without_accents = "".join(
            char
            for char in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(char) != "Mn"
        )

        return re.sub(r"\s+", " ", without_accents)
