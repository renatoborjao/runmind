"""HIGIENE da análise escrita pela IA — o que NUNCA pode chegar ao atleta, não importa o
que o modelo escreva. São impossibilidades de FATO e regras que o Renato já decidiu
(não decisões do coach, que seguem com a IA — [[feedback_ia_decide_sem_regras]]):

- **Sem FC, sem frequência cardíaca no texto.** O Hélio corre sem relógio (0 de 92
  corridas com FC) e a análise dizia "frequência cardíaca na Z4" e mandava "manter a
  frequência abaixo de 141 bpm": a zona vinha estimada do PACE e o teto, da idade.
- **Sem jargão de carga.** "Carga aguda subindo para 1,48" vazou pro atleta
  ([[feedback_sem_jargao_metricas]]).
- **Sem estado interno inventado** ("segure a ansiedade": ele nunca disse que estava ansioso).
- **Sem contar vezes.** "Pela quinta vez recente…" / "É a sexta vez…" sem as datas que a voz do
  coach exige — contagem sem lastro, e repetida a cada corrida, vira bronca que não muda nada.

Tira a FRASE (ou só a oração) que fere a regra e preserva o resto — melhor um texto mais curto
e verdadeiro que um com número impossível. Puro/determinístico."""

from __future__ import annotations

import re
from dataclasses import replace

# --- frequência cardíaca ----------------------------------------------------------------------
_HR = re.compile(
    r"\b(?:frequ[eê]ncia\s+card[ií]aca|FC|bpm|batimentos?|card[ií]ac[oa]s?"
    r"|teto\s+a[eé]r[oó]bic[oa]|Z[1-5]"
    r"|zonas?\s+(?:de\s+)?(?:FC|frequ[eê]ncia|[1-5]|a[eé]r[oó]bic[oa]))\b",
    re.IGNORECASE,
)

# --- jargão de carga / enums internos ---------------------------------------------------------
_JARGON = re.compile(
    r"\b(?:ACWR|carga\s+aguda|carga\s+cr[oô]nica|aguda\s*(?:/|:|x)\s*cr[oô]nica"
    r"|DETRAINING|STRAINED|ABSORBING|RECOVERY_FLAG|BALANCED)\b",
    re.IGNORECASE,
)

# --- tique de linguagem ------------------------------------------------------------
# "cravou/cravada/cravado" saiu em 8 trechos de 5 atletas e voltou na checagem com o
# modelo real ("ritmo e acelerações cravados dentro do alvo"). A voz do coach já pede
# elogio com número; aqui a muleta vira palavra de verdade.
_TICS = (
    (re.compile(r"\bcravou\b", re.IGNORECASE), "fechou"),
    (re.compile(r"\bcravaram\b", re.IGNORECASE), "fecharam"),
    (re.compile(r"\bcravando\b", re.IGNORECASE), "mantendo"),
    (re.compile(r"\bcravar\b", re.IGNORECASE), "manter"),
    (re.compile(r"\bcravad[oa]s\b", re.IGNORECASE), "firmes"),
    (re.compile(r"\bcravad[oa]\b", re.IGNORECASE), "firme"),
)

# --- estado interno que o atleta não contou -------------------------------------------------
# A voz do coach proíbe falar de estado interno que ele não contou ("segure a ansiedade" em vez de
# "segure o ritmo na faixa X") e o modelo ainda escorrega (Leonardo 19/10, Renato2 18/10). Na
# análise de um TREINO não há relato de ansiedade a citar: a oração sai.
_INTERNAL_STATE = re.compile(r"\b(?:ansiedade|ansios[oa]s?)\b", re.IGNORECASE)

# --- contagem de vezes ("pela quinta vez recente", "é a sexta vez que") -----------------------
_ORDINAL = (
    "primeira|segunda|terceira|quarta|quinta|sexta|s[eé]tima|oitava|nona|"
    "d[eé]cima"
)

_COUNT = re.compile(
    rf"\b(?:pela|na|j[aá]\s+[ée]\s+a|[ée]\s+a|foi\s+a)\s+(?:{_ORDINAL})\s+vez"
    r"(?:\s+recente)?(?:\s+que)?\s*,?\s*",
    re.IGNORECASE,
)

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# onde uma frase se parte em orações (vírgula, dois-pontos, ponto e vírgula, travessão, "para")
# ("para"/"pra" só parte a frase antes de um VERBO no infinitivo: "para manter…", não "para 1.48")
_CLAUSE = re.compile(
    r"(,\s+|;\s+|:\s+|\s+—\s+|\s+(?:para|pra)\s+(?=[a-zà-ú]+(?:ar|er|ir|or)\b))",
    re.IGNORECASE,
)

# o que sobra de uma frase só vale se ainda for uma frase: tantas palavras e uma fração do
# original (senão vira fragmento: "Rodar 2 km a mais.")
_MIN_WORDS = 5
_MIN_KEPT_FRACTION = 0.4

# dentro de uma oração que fere a regra, onde dá pra separar o que presta ("fez 6 km com pace
# médio de 5:40/km **e frequência cardíaca na Z4**")
_SUBCLAUSE = re.compile(r"(\s+(?:e|com)\s+)")


def _capitalize(text: str) -> str:

    return text[:1].upper() + text[1:] if text else text


def _trim_clause(clause: str, pattern: re.Pattern) -> str:
    """A oração sem os pedaços (separados por "e"/"com") que ferem a regra; vazio se nada presta."""

    if not pattern.search(clause):

        return clause

    parts = _SUBCLAUSE.split(clause)

    pieces = parts[0::2]

    joints = parts[1::2]

    kept_text = ""

    previous_kept = False

    for index, piece in enumerate(pieces):

        if pattern.search(piece):

            previous_kept = False

            continue

        if kept_text:

            kept_text += (joints[index - 1] if previous_kept else " ") + piece

        else:

            kept_text = piece

        previous_kept = True

    return kept_text if len(kept_text.split()) >= 3 else ""


def _drop_from_sentence(sentence: str, pattern: re.Pattern) -> str | None:
    """A frase sem o que casa `pattern` (orações e, dentro delas, pedaços com "e"/"com");
    None se o que sobra não é mais uma frase que preste."""

    if not pattern.search(sentence):

        return sentence

    parts = _CLAUSE.split(sentence)

    clauses = parts[0::2]

    delimiters = parts[1::2]

    kept_text = ""

    previous_kept = False

    for index, clause in enumerate(clauses):

        trimmed = _trim_clause(clause.rstrip(".!? "), pattern).strip()

        # um "pedaço" de uma palavra só ("1.48") não é oração
        if len(trimmed.split()) < 2:

            previous_kept = False

            continue

        if kept_text:

            # oração vizinha de uma que ficou: mantém o conector original; depois de
            # uma que caiu, une com vírgula
            joint = delimiters[index - 1] if previous_kept else ", "

            kept_text += joint + trimmed

        else:

            kept_text = trimmed

        previous_kept = True

    kept_text = kept_text.strip(" ,;—")

    original_words = max(1, len(sentence.split()))

    kept_words = len(kept_text.split())

    if kept_words < _MIN_WORDS or kept_words / original_words < _MIN_KEPT_FRACTION:

        return None

    ends = sentence.rstrip()[-1:] if sentence.rstrip() else ""

    return _capitalize(kept_text) + (ends if ends in ".!?" else "")


def _scrub(text: str, pattern: re.Pattern) -> str | None:

    kept = []

    for sentence in _SENTENCE_END.split(text.strip()):

        trimmed = _drop_from_sentence(sentence, pattern)

        if trimmed:

            kept.append(trimmed)

    return " ".join(kept) or None


def swap_tics(text: str) -> str:
    """Troca as muletas ("cravou", "cravados") por palavras que dizem a coisa, preservando a
    maiúscula do início."""

    for pattern, word in _TICS:

        text = pattern.sub(
            lambda m, w=word: w.capitalize() if m.group(0)[:1].isupper() else w, text,
        )

    return text


def strip_repeat_counts(text: str) -> str:
    """Tira "pela quinta vez recente"/"é a sexta vez que" — a contagem sem as datas."""

    if not _COUNT.search(text):

        return text

    return _capitalize(_COUNT.sub("", text).strip())


def clean_text(text: str | None, *, has_hr: bool) -> str | None:
    """Um campo da análise já limpo; None se não sobrou nada que preste."""

    if not text or not text.strip():

        return None

    cleaned = swap_tics(strip_repeat_counts(text))

    cleaned = _scrub(cleaned, _JARGON)

    if cleaned:

        cleaned = _scrub(cleaned, _INTERNAL_STATE)

    if cleaned and not has_hr:

        cleaned = _scrub(cleaned, _HR)

    return cleaned


def sanitize(analysis, *, has_hr: bool):
    """A `AIAnalysis` limpa (mesmo tipo), ou None se a análise toda caiu — o pipeline
    então cai no texto determinístico, como sempre faz quando a IA falha."""

    bullets = [
        text
        for text in (clean_text(b, has_hr=has_hr) for b in analysis.analysis)
        if text
    ]

    if not bullets:

        return None

    return replace(
        analysis,
        headline=clean_text(analysis.headline, has_hr=has_hr),
        analysis=bullets,
        attention=clean_text(analysis.attention, has_hr=has_hr),
        next_step=clean_text(analysis.next_step, has_hr=has_hr),
    )
