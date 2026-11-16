"""ÚLTIMA DOSE DE CADA ESTÍMULO — a escada da evolução, como DADO pro coach.

O coach recebia, de cada família de treino, só QUANDO foi feita pela última vez ("limiar: último
há 3 dias") — não a DOSE. Sem saber que o último limiar foi "3,5 km contínuos a 6:15-6:25", ele não
tinha como dar o degrau seguinte do mesmo estímulo e trocava de família toda semana (fartlek →
limiar → VO2 → fartlek), variando sem progredir: 125 treinos das últimas 8 semanas dos 6 atletas,
todos com estrutura diferente, nenhum com a mesma dose avançando (21/10).

Aqui sai a dose como o coach a escreveu (as linhas do trabalho principal, sem aquecimento nem
dica), de cada estímulo que PROGRIDE (forte, longão, moderado), as duas últimas, e se o atleta fez.
É DADO + CONHECIMENTO, nunca cota nem fórmula ([[feedback_ia_decide_sem_regras]]): o coach decide se
avança a mesma dose, repete, troca ou recua — o que a evolução × meta × objetivo pedir.
Puro/determinístico."""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.application.history.stimulus_ledger import (
    FARTLEK,
    HILLS,
    LONG,
    PROGRESSION,
    RACE_PACE,
    STEADY,
    THRESHOLD,
    VO2,
    StimulusLedger,
)
from app.domain.entities.activity import Activity
from app.domain.entities.training_plan import TrainingPlan
from app.domain.value_objects.sports import is_run_sport

# estímulos que PROGRIDEM em dose (a leve/regenerativa e as acelerações não têm "degrau")
PROGRESSIVE = (THRESHOLD, VO2, RACE_PACE, FARTLEK, PROGRESSION, HILLS, STEADY, LONG)

# quantas doses por estímulo (a última e a anterior mostram a direção)
PER_FAMILY = 2

WINDOW_WEEKS = 8

# linhas da estrutura que NÃO são a dose (aquecer, soltar, dica, foco)
_NOT_DOSE = ("aquecimento", "desaquecimento", "dica", "foco")

_MAX_CHARS = 190

_MIN_RUN_M = 1000


@dataclass(slots=True)
class Dose:

    family: str
    day: date
    workout_type: str
    main: str
    done: bool
    # a faixa de ritmo do trabalho principal (min/km, rápida → lenta), quando dá pra ler
    band: tuple[float, float] | None = None


# famílias cuja faixa tem uma RÉGUA de hoje (o ritmo calibrado dele ou o ritmo da meta)
RULED = (THRESHOLD, VO2, RACE_PACE)

# diferença (s/km) abaixo da qual a faixa está "na régua"
_RULER_TOLERANCE_S = 8

# rótulos da parte principal e das partes que não são a dose (como o coach costuma escrever)
_MAIN_LABELS = ("principal", "série", "serie", "bloco", "tiros", "blocos")

_SIDE_LABELS = (
    "início", "inicio", "aquec", "solt", "retorno", "volta à calma", "desaquec", "recupera",
    "trote", "calma",
)

_BAND = re.compile(r"(\d{1,2}):(\d{2})\s*(?:/km)?\s*(?:a|-|–|—|até)\s*(\d{1,2}):(\d{2})")


def _pace(text: str | None) -> float | None:

    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", text or "")

    return int(match[1]) + int(match[2]) / 60 if match else None


def pace_band(main: str, low: str | None = None, high: str | None = None) -> tuple[float, float] | None:
    """A faixa do trabalho principal: a "m:ss a m:ss" da parte que o coach chamou de série/bloco
    principal (ou da primeira parte que não é soltar/voltar/recuperar); sem ela, a faixa da sessão.
    (rápida, lenta) em min/km. O "Início livre: 1 km leve (6:09 a 6:49)" não é a dose."""

    parts = [p.strip() for p in (main or "").split(" · ") if p.strip()]

    def label(part: str) -> str:

        return part.split(":", 1)[0].lower() if ":" in part[:40] else ""

    principal = [p for p in parts if any(k in label(p) for k in _MAIN_LABELS)]

    others = [p for p in parts if not any(k in label(p) for k in _SIDE_LABELS)]

    match = None

    for part in principal + others:

        match = _BAND.search(part)

        if match:

            break

    if match:

        a = int(match[1]) + int(match[2]) / 60

        b = int(match[3]) + int(match[4]) / 60

        return (min(a, b), max(a, b))

    a, b = _pace(low), _pace(high)

    if a and b:

        return (min(a, b), max(a, b))

    return None


def _fmt(pace: float) -> str:

    total = round(pace * 60)

    return f"{total // 60}:{total % 60:02d}"


def ruler_lines(doses: dict[str, list[Dose]], ruler: dict[str, float]) -> list[str]:
    """A ÚLTIMA faixa de cada forte contra a RÉGUA DE HOJE (limiar e VO2 calibrados dele, ritmo da
    meta). Só sai o que diverge — faixa que ficou lenta ou rápida demais — e a faixa de limiar mais
    lenta que o ritmo da prova. Dado pro coach: quem ENTREGA uma faixa que ficou lenta não evolui
    com +5 s sobre ela."""

    out: list[str] = []

    for family in RULED:

        today = ruler.get(family)

        last = next((d for d in doses.get(family, []) if d.band), None)

        if not today or last is None:

            continue

        fast, slow = last.band

        band = f"{_fmt(fast)}–{_fmt(slow)}"

        gap_fast = round((fast - today) * 60)

        gap_slow = round((slow - today) * 60)

        if gap_fast > _RULER_TOLERANCE_S:

            out.append(
                f"- {family}: a régua de hoje é {_fmt(today)}; a última faixa ({band}, "
                f"{last.day:%d/%m}) está {gap_fast}–{gap_slow} s/km MAIS LENTA que ela."
            )

        elif gap_slow < -_RULER_TOLERANCE_S:

            out.append(
                f"- {family}: a régua de hoje é {_fmt(today)}; a última faixa ({band}, "
                f"{last.day:%d/%m}) está {abs(gap_slow)}–{abs(gap_fast)} s/km MAIS RÁPIDA que ela."
            )

    race = ruler.get(RACE_PACE)

    threshold = next((d for d in doses.get(THRESHOLD, []) if d.band), None)

    if race and threshold and (threshold.band[0] - race) * 60 > _RULER_TOLERANCE_S:

        out.append(
            f"- a última faixa de limiar ({_fmt(threshold.band[0])}–{_fmt(threshold.band[1])}) é "
            f"MAIS LENTA que o ritmo da meta ({_fmt(race)}/km)."
        )

    return out


_RULER_KNOWLEDGE = (
    "CONHECIMENTO, não regra: a régua de hoje é a capacidade ATUAL dele (calibrada pelo que ele "
    "entregou e pelo relógio) e o ritmo da meta. A faixa nova de cada forte nasce DELA — não de "
    "alguns segundos sobre a faixa antiga, que foi escrita com a régua de semanas atrás. Fisiologia: "
    "o limiar é o ritmo sustentável por ~1 hora — mais rápido que o de meia e maratona, perto do "
    "ritmo de 10 km de quem corre os 10 km em ~1 h; limiar mais lento que o ritmo-alvo da prova "
    "dele não treina o que a prova cobra. Se ele vem ENTREGANDO os fortes, a faixa sobe até a "
    "régua (em degrau, se o salto for grande, e dito no propósito); se NÃO entrega, a régua pode "
    "estar otimista — aí recalibre pelo que ele fez. E não chame de 'mais firme' uma faixa que "
    "segue mais lenta que a régua ou que a meta."
)


def main_lines(structure: str | None) -> str:
    """O trabalho principal de uma sessão, como o coach escreveu: as linhas da estrutura sem
    aquecimento, desaquecimento, dica e foco, numa linha só."""

    kept = []

    for raw in (structure or "").splitlines():

        line = raw.strip()

        if not line:

            continue

        label = line.split(":", 1)[0].strip().lower()

        if any(label.startswith(skip) for skip in _NOT_DOSE):

            continue

        kept.append(line)

    text = " · ".join(kept)

    return text if len(text) <= _MAX_CHARS else text[: _MAX_CHARS - 1].rstrip() + "…"


def last_doses(
    plans: list[TrainingPlan],
    activities: list[Activity],
    today: date,
    weeks: int = WINDOW_WEEKS,
) -> dict[str, list[Dose]]:
    """Por estímulo que progride: as últimas `PER_FAMILY` doses PRESCRITAS (da mais recente pra
    mais antiga) e se foram feitas. Sessão futura sem corrida casada não entra."""

    from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher

    start = today - timedelta(weeks=weeks)

    runs = [a for a in activities if is_run_sport(a.sport) and (a.distance or 0) >= _MIN_RUN_M]

    by_week = {p.week_start: p for p in plans}

    found: dict[str, list[Dose]] = {}

    for plan in by_week.values():

        for session, act in WeeklyPlanMatcher.pairs(plan, runs):

            if getattr(session, "kind", "run") not in ("run", "walk", "run_walk"):

                continue

            family = StimulusLedger.classify(session.workout_type)

            if family not in PROGRESSIVE:

                continue

            day = plan.session_date(session)

            if day < start or (day > today and act is None):

                continue

            main = main_lines(session.structure)

            if not main:

                continue

            band = pace_band(
                main, getattr(session, "target_pace_min", None),
                getattr(session, "target_pace_max", None),
            )

            found.setdefault(family, []).append(
                Dose(family, day, session.workout_type, main, act is not None, band),
            )

    return {
        family: sorted(doses, key=lambda d: d.day, reverse=True)[:PER_FAMILY]
        for family, doses in found.items()
    }


def _label(day: date) -> str:

    return f"{day:%d/%m}"


def render(
    doses: dict[str, list[Dose]],
    today: date,
    plan_voice: bool = True,
    ruler: dict[str, float] | None = None,
) -> str:
    """As doses como linhas pro prompt. Com `plan_voice`, vem junto o CONHECIMENTO de como a
    escada costuma render (e que a decisão é do coach). `ruler`: a régua de hoje por família
    (min/km) — a última faixa que divergir dela sai marcada. Vazio sem dose."""

    if not doses:

        return ""

    order = [f for f in PROGRESSIVE if f in doses]

    lines = [
        "ÚLTIMA DOSE DE CADA ESTÍMULO (a escada da evolução: o que VOCÊ prescreveu e se ele "
        "fez; da mais recente pra mais antiga):"
    ]

    for family in order:

        parts = []

        for dose in doses[family]:

            status = "feito" if dose.done else "NÃO feito"

            parts.append(f"{_label(dose.day)} ({status}): {dose.main}")

        lines.append(f"- {family}: " + " ‖ antes, ".join(parts))

    if plan_voice:

        lines.append(
            "CONHECIMENTO, não regra: o MESMO estímulo subindo em degrau mensurável (uma "
            "repetição a mais, bloco maior, pace mais perto do alvo, pausa menor) costuma render "
            "mais evolução que trocar de estímulo toda semana — trocar é variar, não evoluir. Mas "
            "a decisão é sua, pelo que a evolução × a meta × o objetivo dele pedem agora: avance "
            "a dose, repita (e diga por quê), troque (lacuna, fase, corpo, preferência dele) ou "
            "recue. No propósito de cada sessão diga o que mudou em relação à última dose do "
            "mesmo tipo — ou por que não mudou."
        )

    diverging = ruler_lines(doses, ruler or {})

    if diverging:

        lines.append("RÉGUA DE HOJE × A ÚLTIMA FAIXA DE CADA FORTE:")

        lines.extend(diverging)

        if plan_voice:

            lines.append(_RULER_KNOWLEDGE)

    return "\n".join(lines)
