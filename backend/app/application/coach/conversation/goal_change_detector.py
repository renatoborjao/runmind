import re
import unicodedata

# portão determinístico BARATO: só chama a IA se a mensagem cheira a pedido
# de troca de OBJETIVO/meta (evita 1 chamada Gemini em toda mensagem que só
# cita "prova" ou "meta" à toa — ex.: perguntas sobre a próxima prova).
_GOAL_WORDS = ["objetivo", "meta", "prova"]

_CHANGE_CUES = [
    "mudar", "muda", "mudou", "trocar", "troca", "trocou", "nova", "novo",
    "atualizar", "atualiza", "agora", "virou", "passar", "passa",
    "redefinir", "redefine",
]

# Gatilho ESTRITO (só verbos claros de trocar), sem os fracos como "agora":
# usado pra decidir se o coach ARMA o estado de "esperando a meta nova" quando
# o atleta quer trocar mas ainda não disse pra quê. Evita que um falso-positivo
# do portão barato ("minha prova foi ótima agora") vire uma pergunta à toa.
_EXPLICIT_CHANGE_CUES = [
    "mudar", "muda", "mudei", "trocar", "troca", "troquei", "redefinir",
    "redefine", "atualizar", "atualiza", "novo objetivo", "nova meta",
    "outro objetivo", "outra meta", "novos objetivos", "outros objetivos",
]


class GoalChangeDetector:
    """Detecta, de forma barata, um pedido de trocar o objetivo/meta do
    atleta ("quero mudar minha meta pra sub-45", "meu objetivo agora é
    saúde"). Falso positivo só custa 1 chamada de IA na extração seguinte —
    ela devolve vazio se não for de fato uma declaração de objetivo."""

    @staticmethod
    def looks_like_goal_change(text: str) -> bool:

        norm = GoalChangeDetector._normalize(text)

        has_goal_word = any(word in norm for word in _GOAL_WORDS)

        has_cue = any(cue in norm for cue in _CHANGE_CUES)

        return has_goal_word and has_cue

    @staticmethod
    def is_explicit_change_request(text: str) -> bool:
        """Pedido CLARO de trocar o objetivo ('quero trocar meus objetivos',
        'mudar minha meta') — mesmo sem dizer pra quê ainda. Só aqui o coach
        arma o estado de espera e pergunta qual é a meta nova."""

        norm = GoalChangeDetector._normalize(text)

        has_goal_word = any(word in norm for word in _GOAL_WORDS)

        has_explicit = any(cue in norm for cue in _EXPLICIT_CHANGE_CUES)

        return has_goal_word and has_explicit

    @staticmethod
    def _normalize(text: str) -> str:

        lowered = text.lower().strip()

        without_accents = "".join(
            char
            for char in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(char) != "Mn"
        )

        return re.sub(r"\s+", " ", without_accents)
