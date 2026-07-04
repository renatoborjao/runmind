import re
import unicodedata
from enum import Enum


class ChatIntent(str, Enum):
    """Perguntas que têm resposta canônica e completa no sistema —
    respondê-las de forma determinística evita que o Gemini resuma ou
    reformate (e desconfigure) dados que já temos prontos."""

    LAST_TRAINING = "LAST_TRAINING"

    NEXT_TRAINING = "NEXT_TRAINING"


# Pedido claro sobre o treino JÁ FEITO (quer a análise completa).
_LAST_PATTERNS = [
    r"como (foi|ficou|fiquei|fui|foi que foi)\b.*\b(treino|corrida|rodagem|correr|corri|longao)",
    r"\b(ultimo treino|ultima corrida|treino passado|treino de ontem)\b.*\b(como|analise|resultado|resumo|mostra|ver|detalh)",
    r"\b(analise|resultado|resumo|feedback|balanco)\b.*\b(treino|corrida|rodagem)",
    r"\b(me mostra|mostra|ver|quero ver)\b.*\b(ultimo|ultima)\b.*\b(treino|corrida)",
    r"como que (foi|ficou)\b.*\b(treino|corrida)",
]

# Pedido claro sobre o PRÓXIMO treino (quer a sessão detalhada).
_NEXT_PATTERNS = [
    r"\b(proximo treino|proxima corrida|proximo treinamento|proxima sessao)\b",
    r"\bquando\b.*\b(treino|treinar|corrida|correr|rodar|proxima)\b",
    r"\bqual\b.*\b(proximo|proxima)\b.*\b(treino|corrida)",
    r"\b(treino|corrida) (de|pra|para) (amanha|hoje)\b",
    r"\bqual\b.*\b(meu|o)\b.*\b(treino|corrida)\b.*\b(agora|hoje|amanha|proximo)\b",
    r"\b(o que|oq|o q)\b.*\b(treino|faco|corro|rodo|devo fazer)\b.*\b(hoje|amanha|agora)\b",
]

_LAST_REGEXES = [re.compile(p) for p in _LAST_PATTERNS]

_NEXT_REGEXES = [re.compile(p) for p in _NEXT_PATTERNS]


class IntentRouter:

    @staticmethod
    def detect(text: str) -> ChatIntent | None:
        """Só devolve uma intenção quando o pedido é inequívoco. Se a
        mensagem casa com as duas (ou nenhuma), devolve None e a conversa
        segue para o Gemini — evita mostrar o card errado."""

        normalized = IntentRouter._normalize(text)

        last = any(regex.search(normalized) for regex in _LAST_REGEXES)

        nxt = any(regex.search(normalized) for regex in _NEXT_REGEXES)

        if last and not nxt:

            return ChatIntent.LAST_TRAINING

        if nxt and not last:

            return ChatIntent.NEXT_TRAINING

        return None

    @staticmethod
    def _normalize(text: str) -> str:
        """Minúsculas, sem acento e com espaços colapsados — as regras
        ficam livres de acento ('proximo' cobre 'próximo')."""

        lowered = text.lower().strip()

        without_accents = "".join(
            char
            for char in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(char) != "Mn"
        )

        return re.sub(r"\s+", " ", without_accents)
