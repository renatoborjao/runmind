import re
import unicodedata
from enum import Enum


class ProposalReply(str, Enum):

    CONFIRM = "CONFIRM"

    REJECT = "REJECT"

    # o atleta está CORRIGINDO/refinando a proposta, não aceitando nem
    # recusando ("não é a semana, é o de amanhã", "sim, mas deixa 12km",
    # "prefiro quarta"). NÃO descarta — o coach re-propõe com a correção.
    REFINE = "REFINE"

    # não é sim, não, nem correção clara (mudou de assunto) — quem chama decide
    UNCLEAR = "UNCLEAR"


# Só faz sentido rodar quando HÁ uma proposta pendente: aí "sim/pode/manda"
# é aceite e "nao/deixa/esquece" é recusa. Casamento por palavra inteira pra
# "nao" não pegar dentro de "nao curto" (que seria uma contraproposta).
_CONFIRM = [
    "sim", "isso", "isso ai", "pode", "pode ser", "pode sim", "aplica",
    "aplicar", "manda", "manda ver", "bora", "fechado", "fechou", "topo",
    "perfeito", "aceito", "concordo", "combinado", "ok", "okay", "blz",
    "beleza", "vamos", "valeu", "otimo", "show", "faz isso", "faz",
    "quero sim", "gostei", "aprovado",
    # confirmar aplicando/sincronizando ("certo, atualiza o plano e manda pro
    # relógio") — no contexto de uma proposta pendente é um SIM
    "certo", "atualiza", "atualizar", "atualize", "sincroniza", "sincronizar",
    "confirma", "confirmar", "confirmo", "pode atualizar", "pode aplicar",
]

# "para" NÃO entra aqui: quase sempre é a PREPOSIÇÃO ("digo para semana que
# vem", "para de segunda"), não o verbo parar — casava recusa em cima de um
# aceite qualificado e descartava a proposta (bug real 02/08). Recusa de
# verdade já é coberta por nao/deixa/esquece/cancela.
_REJECT = [
    "nao", "nem", "deixa", "esquece", "melhor nao", "prefiro nao",
    "agora nao", "deixa quieto", "deixa pra la", "nao quero", "nao precisa",
    "cancela", "negativo",
]

# "sim, MAS prefiro quarta" é um aceite qualificado (na prática, uma
# contraproposta) — não pode virar aplicação automática.
_ADVERSATIVE = [
    "mas", "porem", "so que", "contudo", "todavia", "no entanto",
    "entretanto",
]

# o atleta está CORRIGINDO o escopo/conteúdo da proposta (não recusando):
# "não é a semana, é o de amanhã", "na verdade só o longão", "quis dizer...".
# Trata como REFINE — re-propõe, não descarta. Bug real do Renato: "não é o
# da semana, é o de amanhã" era lido como "não" e o coach jogava tudo fora.
_CORRECTION = [
    "na verdade", "quis dizer", "queria dizer", "nao e o", "nao e a",
    "nao e isso", "nao era", "nao e esse", "nao e essa", "e o de", "e a de",
    "so o", "so a", "apenas o", "apenas a",
]


class ProposalReplyDetector:

    @staticmethod
    def detect(text: str) -> ProposalReply:

        norm = ProposalReplyDetector._normalize(text)

        rejects = ProposalReplyDetector._has_any(norm, _REJECT)

        confirms = ProposalReplyDetector._has_any(norm, _CONFIRM)

        adversative = ProposalReplyDetector._has_any(norm, _ADVERSATIVE)

        correction = ProposalReplyDetector._has_any(norm, _CORRECTION)

        # CORREÇÃO/contraproposta ganha antes de tudo: "não é a semana, é o de
        # amanhã" / "sim, mas 12km" — não é recusa nem aceite, é refino. O
        # coach re-propõe (não descarta).
        if correction or adversative:

            return ProposalReply.REFINE

        # recusa clara (sem correção): "não", "deixa", "esquece"
        if rejects:

            return ProposalReply.REJECT

        # aceite limpo
        if confirms:

            return ProposalReply.CONFIRM

        return ProposalReply.UNCLEAR

    @staticmethod
    def _has_any(norm: str, cues: list[str]) -> bool:

        return any(
            re.search(rf"(?:^|\s){re.escape(cue)}(?:$|\s|[.,!?])", norm)
            for cue in cues
        )

    @staticmethod
    def _normalize(text: str) -> str:

        lowered = text.lower().strip()

        without_accents = "".join(
            char
            for char in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(char) != "Mn"
        )

        return re.sub(r"\s+", " ", without_accents)
