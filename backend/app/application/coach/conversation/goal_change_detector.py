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

# Pistas de ADICIONAR um objetivo (não trocar): o atleta quer SOMAR uma meta
# às que já tem ("além disso quero...", "também tenho o objetivo de..."). Sem
# elas, um pedido de meta é tratado como TROCA (sobrescreve). Ver design A de
# múltiplos objetivos concorrentes ([[project_multiplos_objetivos]]).
_ADD_CUES = [
    "tambem", "alem disso", "alem de", "alem da", "somar", "adicionar",
    "acrescentar", "sem deixar de", "sem abandonar", "sem abrir mao",
    "sem parar de", "junto com", "ao mesmo tempo", "em paralelo", "mais um",
    "mais uma meta", "outro objetivo tambem", "continuo querendo",
    "continuar querendo", "e ainda",
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

        has_cue = any(cue in norm for cue in _CHANGE_CUES) or any(
            cue in norm for cue in _ADD_CUES
        )

        return has_goal_word and has_cue

    @staticmethod
    def is_additional_objective(text: str) -> bool:
        """O atleta quer SOMAR uma meta às que já tem (não trocar) — 'além da
        prova, quero emagrecer', 'também tenho o objetivo de correr 21k'.
        Requer palavra de meta + pista de adição, pra não confundir com troca."""

        norm = GoalChangeDetector._normalize(text)

        has_goal_word = any(word in norm for word in _GOAL_WORDS)

        has_add = any(cue in norm for cue in _ADD_CUES)

        return has_goal_word and has_add

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
