"""ELE PEDE MAIS — o atleta disse que os treinos estão leves/fracos, que aguenta mais, que quer mais
carga. É DADO (a pessoa que sente o treino), pesado JUNTO do corpo e do esforço percebido — nunca
ignorado em silêncio.

Caso real (Leonardo, 21/10): em 02/10 escreveu que achava as metas e os treinos muito leves, em
18/10 que "estava demorando muito pra chegar ao objetivo"; o relato ficou numa linha do dossiê e a
dose não mudou por 19 dias, com o esforço percebido ≤3/10 em 6 de 7 corridas e 0% de tempo em zona
forte. O que ele diz de si pesa junto dos números ([[feedback_ia_decide_sem_regras]] — dado +
conhecimento + "decida"): se os dados confirmam, a resposta é DOSE; se não, a resposta é o dado.
Puro/determinístico (frases do próprio atleta; o julgamento é da IA)."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean

# quanto tempo um pedido continua valendo como sinal
WINDOW_DAYS = 28

# esforço percebido que conta como "leve pra ele"
_EASY_RPE = 3

_MAX_QUOTE = 150

# frases do atleta (sem acento, minúsculas). Só o GERAL — "o treino de hoje foi leve", "treino leve"
# e "pace leve" (o TIPO de treino) não são pedido; "não dá pra aumentar"/"não aguento mais" são o
# contrário (a negação corta).
_NOT = r"(?<!nao\s)(?<!\bn\s)(?<!nem\s)"

_EASY_WORD = r"(?:leves?|fracos?|faceis|facil|moles?)"

_PATTERNS = [
    re.compile(p)
    for p in (
        # "os treinos muito leve", "treinos demais fracos"
        r"treinos?\s+(?:\w+\s+){0,2}?(?:muito|demais|bem|meio|super|bastante)\s+(?:\w+\s+)?"
        + _EASY_WORD,
        # "treinos estão fracos", "treinos ficaram leves"
        r"treinos?\s+(?:estao|esta|ta|tao|sao|ficaram|andam|tem sido|vem sendo)\s+(?:\w+\s+)?"
        + _EASY_WORD,
        # "achando os treinos leves", "acho os treinos fracos"
        r"(?:achando|acho|achei|acha|achar)\s+(?:os\s+|meus\s+)?treinos?\s+(?:\w+\s+)?"
        + _EASY_WORD,
        r"(?:metas?|distancias?)\s+(?:\w+\s+){0,2}?(?:baixas?|fracas?|faceis|facil)",
        _NOT + r"aguent[oa]\s+mais",
        _NOT + r"da\s+pra\s+(?:puxar|aumentar|fazer\s+mais|correr\s+mais)",
        _NOT + r"(?:posso|consigo)\s+(?:puxar|aumentar|fazer\s+mais|correr\s+mais)",
        r"(?:queria|quero|gostaria\s+de|preciso)\s+(?:de\s+)?"
        r"(?:mais\s+(?:treinos?|distancias?|km|quilometragem|carga|intensidade|desafio)"
        r"|treinar\s+mais|correr\s+mais|puxar\s+mais"
        r"|treinos?\s+mais\s+(?:fortes?|puxados?|pesados?|intensos?))",
        r"poucas?\s+(?:distancias?|quilometragens?|km|carga)",
        r"demorando\s+(?:muito\s+)?(?:pra|para)\s+(?:chegar|atingir|evoluir)",
    )
]


@dataclass(slots=True)
class Ask:

    day: date
    quote: str
    source: str  # "conversa" | "check-in"


def _normalize(text: str) -> str:

    decomposed = unicodedata.normalize("NFKD", text.lower())

    return "".join(c for c in decomposed if not unicodedata.combining(c))


def says_more(text: str | None) -> bool:
    """O texto do atleta diz que quer/aguenta mais ou acha os treinos leves?"""

    if not text:

        return False

    norm = _normalize(text)

    return any(p.search(norm) for p in _PATTERNS)


def _quote(text: str) -> str:

    flat = " ".join(text.split())

    return flat if len(flat) <= _MAX_QUOTE else flat[: _MAX_QUOTE - 1].rstrip() + "…"


def find(
    turns: list[dict], checkins: list, today: date, window_days: int = WINDOW_DAYS,
) -> list[Ask]:
    """Os pedidos recentes, do mais antigo pro mais novo. `turns` = a conversa (dicts com
    timestamp/role/text); `checkins` = os check-ins (day/note)."""

    cutoff = today - timedelta(days=window_days)

    found: list[Ask] = []

    for turn in turns or []:

        if turn.get("role") != "user":

            continue

        try:

            day = date.fromisoformat(str(turn.get("timestamp") or "")[:10])

        except ValueError:

            continue

        text = str(turn.get("text") or "")

        if cutoff <= day <= today and says_more(text):

            found.append(Ask(day, _quote(text), "conversa"))

    for checkin in checkins or []:

        note = getattr(checkin, "note", None)

        try:

            day = date.fromisoformat(getattr(checkin, "day", ""))

        except (ValueError, TypeError):

            continue

        if note and cutoff <= day <= today and says_more(note):

            found.append(Ask(day, _quote(note), "check-in"))

    return sorted(found, key=lambda a: a.day)


def _rpe_line(rpes: list[int]) -> str:

    if not rpes:

        return "sem esforço percebido registrado"

    easy = sum(1 for r in rpes if r <= _EASY_RPE)

    return f"esforço percebido ≤{_EASY_RPE}/10 em {easy} de {len(rpes)} corridas recentes"


def _dose_line(since: dict | None) -> str:

    if not since:

        return ""

    return (
        f"Antes do pedido: ~{since['before_week']:.0f} km/semana e maior treino "
        f"{since['before_long']:.1f} km. Desde então: ~{since['after_week']:.0f} km/semana e "
        f"maior treino {since['after_long']:.1f} km."
    )


def dose_since(activities: list, first_ask: date, today: date) -> dict | None:
    """A dose (km/semana em semana de corrida e maior treino) nas 3 semanas ANTES do primeiro
    pedido × da semana do pedido até a última semana fechada. None sem dado dos dois lados."""

    from app.application.history.weekly_buckets import activity_date
    from app.domain.value_objects.sports import is_run_sport

    def monday(day: date) -> date:

        return day - timedelta(days=day.weekday())

    ask_week = monday(first_ask)

    this_week = monday(today)

    runs = [
        (activity_date(a), a.distance / 1000)
        for a in activities
        if is_run_sport(a.sport) and a.distance
    ]

    def window(start: date, end: date) -> tuple[list[float], float]:

        weeks: dict[date, float] = {}

        longest = 0.0

        for day, km in runs:

            if start <= day < end:

                weeks[monday(day)] = weeks.get(monday(day), 0.0) + km

                longest = max(longest, km)

        return list(weeks.values()), longest

    before_weeks, before_long = window(ask_week - timedelta(weeks=3), ask_week)

    after_weeks, after_long = window(ask_week, this_week)

    if not before_weeks or not after_weeks:

        return None

    return {
        "before_week": mean(before_weeks),
        "before_long": before_long,
        "after_week": mean(after_weeks),
        "after_long": after_long,
    }


def asks_more_directive(
    asks: list[Ask],
    rpes: list[int],
    hard_pct: int | None,
    body: str | None,
    since: dict | None,
) -> str:
    """Pro PLANO: o pedido + o que os dados dizem + a obrigação de responder com dose ou com o
    dado. Vazio sem pedido."""

    if not asks:

        return ""

    said = "; ".join(f'em {a.day:%d/%m} ({a.source}) "{a.quote}"' for a in asks[-2:])

    hard = f"{hard_pct}% do tempo em zona forte (4 sem)" if hard_pct is not None else ""

    facts = ", ".join(x for x in (_rpe_line(rpes), hard, f"corpo: {body}" if body else "") if x)

    return (
        "ELE PEDE MAIS (dado dele — pese JUNTO do corpo e do esforço percebido; não é ordem nem "
        f"dá pra ignorar): disse {said}. O que os números dizem: {facts}. "
        f"{_dose_line(since)} Se os números SUSTENTAM o pedido (esforço baixo, corpo firme), a "
        "resposta é DOSE: mais volume no longão e mais tempo em qualidade de verdade — não só um "
        "dia a mais — e diga a ele o que mudou e por quê. Se NÃO sustentam (esforço alto, "
        "recuperação caindo), diga isso a ele com o dado. Deixar a semana igual sem dizer nada é "
        "o único erro."
    ).replace("  ", " ")


def asks_more_fact(
    asks: list[Ask], rpes: list[int], hard_pct: int | None, since: dict | None,
) -> str:
    """O mesmo como FATO CURTO pras vozes que não montam o plano."""

    if not asks:

        return ""

    last = asks[-1]

    hard = f"; {hard_pct}% do tempo em zona forte (4 sem)" if hard_pct is not None else ""

    return (
        f'Ele pediu mais em {last.day:%d/%m}: "{last.quote}". Os números: {_rpe_line(rpes)}{hard}. '
        f"{_dose_line(since)} Responda com isso e não prometa mudança que o plano não fez."
    ).replace("  ", " ")
