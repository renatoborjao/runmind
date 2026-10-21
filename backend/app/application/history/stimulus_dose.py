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

            found.setdefault(family, []).append(
                Dose(family, day, session.workout_type, main, act is not None),
            )

    return {
        family: sorted(doses, key=lambda d: d.day, reverse=True)[:PER_FAMILY]
        for family, doses in found.items()
    }


def _label(day: date) -> str:

    return f"{day:%d/%m}"


def render(doses: dict[str, list[Dose]], today: date, plan_voice: bool = True) -> str:
    """As doses como linhas pro prompt. Com `plan_voice`, vem junto o CONHECIMENTO de como a
    escada costuma render (e que a decisão é do coach). Vazio sem dose."""

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

    return "\n".join(lines)
