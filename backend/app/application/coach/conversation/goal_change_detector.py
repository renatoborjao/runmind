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
    def _normalize(text: str) -> str:

        lowered = text.lower().strip()

        without_accents = "".join(
            char
            for char in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(char) != "Mn"
        )

        return re.sub(r"\s+", " ", without_accents)
