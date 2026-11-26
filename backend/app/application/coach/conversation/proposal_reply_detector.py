import re
import unicodedata
from enum import Enum


class ProposalReply(str, Enum):

    CONFIRM = "CONFIRM"

    REJECT = "REJECT"

    # não é um sim nem um não claros (ex.: contraproposta "prefiro quarta",
    # ou mudança de assunto) — quem chama decide o que fazer
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


# o que pode acompanhar um sim/não numa resposta CURTA e só sobre a pergunta
_SHORT_FILLERS = {
    "a", "o", "as", "os", "e", "ai", "ja", "entao", "por", "favor", "quero",
    "queria", "coloca", "colocar", "inclui", "incluir", "oficializa", "mantem",
    "manter", "fica", "ficar", "assim", "mesmo", "esse", "essa", "dia", "dias",
    "treino", "plano", "no", "na", "meu", "minha", "rit", "ritmind", "coach",
    "claro", "com", "certeza", "boa", "bom", "ta", "obrigado", "obrigada",
    "segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo", "feira",
}


class ProposalReplyDetector:

    @staticmethod
    def is_short_reply(text: str) -> bool:
        """A mensagem INTEIRA é um sim/não (com no máximo enfeite)? Pra ofertas
        que mudam o perfil: um "vamos" no meio de uma frase sobre outra coisa
        ("vamos tirar dezembro de recuperação") não é aceite — bug real 25/11."""

        words = re.findall(r"[a-z0-9]+", ProposalReplyDetector._normalize(text))

        cues = {w for cue in _CONFIRM + _REJECT for w in cue.split()}

        return bool(words) and all(
            w in cues or w in _SHORT_FILLERS or w.isdigit() for w in words
        )

    @staticmethod
    def detect(text: str) -> ProposalReply:

        norm = ProposalReplyDetector._normalize(text)

        rejects = ProposalReplyDetector._has_any(norm, _REJECT)

        confirms = ProposalReplyDetector._has_any(norm, _CONFIRM)

        adversative = ProposalReplyDetector._has_any(norm, _ADVERSATIVE)

        # recusa clara ganha sempre (inclusive "nao, mas...")
        if rejects:

            return ProposalReply.REJECT

        # aceite só se for limpo: "sim, mas..." é contraproposta, não aplica
        if confirms and not adversative:

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
