"""Nome de uma PROVA: o nome PRÓPRIO (sem distância nem palavra genérica) e qual
nome vale quando a MESMA prova (mesma data) chega com nomes diferentes.

O app, a memória do coach e a conversa chamam a mesma prova de jeitos diferentes
("Corrida 10km/15km" no 1º papo, "TF Sports Villa Lobos III (10 km)" quando o
atleta manda o link). A lista dedupa por data — mas o nome ficava o do PRIMEIRO
jeito, genérico, pra sempre (Leonardo, 18/10: a aba Treino seguiu "Corrida
10km/15km" e o coach garantiu que "já estava certinho")."""

import re

_NUMBER_KM = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:km|k|quil[oô]metros?)\b", re.IGNORECASE
)

_GENERIC = {
    "de", "da", "do", "das", "dos", "a", "o", "e", "em", "meia",
    "maratona", "prova", "corrida", "km", "k", "",
}

# nome próprio com menos letras que isso não identifica prova ("tf", "10k")
_MIN_CORE = 4


def proper_core(name: str | None) -> str:
    """O nome PRÓPRIO da prova, sem distância nem palavras genéricas:
    'Santander … Villa-Lobos (15 km)' -> '... villa-lobos'; '15 km' -> '';
    'Corrida 10km/15km' -> ''."""

    text = _NUMBER_KM.sub(" ", (name or "").lower())

    words = [w.strip("()[]—-–,.:;/") for w in text.split()]

    return " ".join(
        w for w in words
        if w not in _GENERIC and not w.isdigit() and any(c.isalpha() for c in w)
    )


def refined_name(current: str | None, new: str | None) -> str | None:
    """O nome que a prova deve passar a ter, ou None pra manter o atual.

    - o novo só vale se tem NOME PRÓPRIO (um "15 km" / "meia maratona" genérico
      nunca troca um nome de verdade);
    - o atual sem nome próprio ("Corrida 10km/15km", "15 km") cede ao novo;
    - o novo que ESTENDE o atual ("Villa-Lobos" -> "TF Sports Villa Lobos III")
      vence; o novo que é só uma versão mais curta do atual, não;
    - dois nomes próprios diferentes pra MESMA data (ninguém corre duas provas
      no mesmo dia): vale o mais recente — é o atleta corrigindo."""

    fresh = (new or "").strip()

    new_core = proper_core(fresh)

    if len(new_core) < _MIN_CORE:

        return None

    current_core = proper_core(current)

    if len(current_core) < _MIN_CORE:

        return fresh

    if new_core == current_core or new_core in current_core:

        return None

    return fresh
