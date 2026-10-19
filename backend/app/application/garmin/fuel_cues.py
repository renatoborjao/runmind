"""AVISO DO GEL DENTRO DO TREINO — o treino longo sobe pro relógio com um passo
curtinho (15 s, no mesmo pace) e a nota "GEL agora" no horário certo de repor.

O horário vem do `FuelingAdvisor` (o mesmo do texto do plano). O relógio apita na
troca de passo e mostra a nota — o atleta não precisa olhar o relógio de pulso nem o
cronômetro. Regras que protegem o treino:

- A GEOMETRIA do treino não muda: o passo é cortado no ponto de DISTÂNCIA que o pace
  planejado leva até o minuto do gel, e o resto do passo encolhe o que o aviso gastou
  (a soma de km fica igual; se o atleta corre mais rápido, o gel chega um pouco mais
  cedo — ±10% de timing é fisiologicamente irrelevante). Passo por TEMPO é cortado por
  tempo.
- Nunca mexe em tiros: gel que cairia dentro de um grupo que repete é descartado.
- Passo aberto (botão lap) ou sem como estimar: fica como está.
- Fisicamente curto demais (< 3 min de cada lado) vira o INÍCIO ou o FIM do passo.

Atrás de canário (`GARMIN_FUEL_CUES_ENABLED` + `GARMIN_FUEL_CUES_PROFILES`) e com
queda automática: se o Garmin recusar o treino com os avisos, sobe sem eles."""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.domain.entities.workout_step import WorkoutStep

# duração do passo de aviso (segundos) — o bastante pra o relógio apitar e mostrar a nota
CUE_SECONDS = 15

# pedaço mínimo (min) de cada lado do aviso; menos que isso o aviso vira início/fim
MIN_SIDE_MINUTES = 3

_EASY_KINDS = {"warmup", "cooldown", "recovery", "rest"}

_FALLBACK_PACE = 6.5  # min/km


@dataclass(slots=True)
class CueStep(WorkoutStep):
    """Passo de aviso: igual ao passo em que cai, com a nota que o relógio mostra."""

    note: str | None = None


def _parse_pace(raw) -> float | None:

    try:

        minutes, seconds = str(raw).strip().split(":")[:2]

        return int(minutes) + int(seconds) / 60

    except (ValueError, TypeError, AttributeError):

        return None


def _pace(step: WorkoutStep, session_pace: float | None) -> float:

    values = [v for v in (_parse_pace(step.pace_min), _parse_pace(step.pace_max)) if v]

    if values:

        return sum(values) / len(values)

    if step.kind in _EASY_KINDS or session_pace is None:

        return _FALLBACK_PACE

    return session_pace


def _leaf_minutes(step: WorkoutStep, session_pace: float | None) -> float:

    if step.duration_sec:

        return step.duration_sec / 60

    if step.distance_m:

        return (step.distance_m / 1000) * _pace(step, session_pace)

    return 0.0


def _span_minutes(steps, session_pace: float | None) -> float:

    total = 0.0

    for step in steps:

        if step.is_repeat:

            total += (step.reps or 1) * _span_minutes(step.steps, session_pace)

        else:

            total += _leaf_minutes(step, session_pace)

    return total


def _label(n: int, total: int, optional: bool, no_gel: bool) -> str:
    """O texto da nota no relógio: SEM emoji (a fonte do relógio não desenha)."""

    if no_gel:

        return f"REPOR agora ({n} de {total}): bala de goma, banana ou isotônico"

    if optional:

        return "GEL (opcional) - com água"

    return f"GEL agora ({n} de {total}) - com água"


def _clamp(offset: float, duration: float) -> float:

    if offset < MIN_SIDE_MINUTES:

        return 0.0

    if duration - offset < MIN_SIDE_MINUTES:

        return duration

    return offset


def _split(
    step: WorkoutStep,
    duration: float,
    cues: list[tuple[float, str]],
    session_pace: float | None,
) -> list[WorkoutStep]:
    """Corta UM passo nos pontos dos avisos, mantendo a soma (km ou tempo) do passo."""

    by_distance = bool(step.distance_m) and not step.duration_sec

    speed = 1000 / (_pace(step, session_pace) * 60)  # m/s

    pieces: list[tuple[str, float | str]] = []

    cursor = 0.0

    for offset, label in cues:

        if offset - cursor > 0.01:

            pieces.append(("run", offset - cursor))

        pieces.append(("cue", label))

        cursor = offset

    if duration - cursor > 0.01:

        pieces.append(("run", duration - cursor))

    run_positions = [i for i, (kind, _) in enumerate(pieces) if kind == "run"]

    if not run_positions:

        return [step]

    last_run = run_positions[-1]

    total = (step.distance_m if by_distance else step.duration_sec) or 0.0

    cue_cost = CUE_SECONDS * speed if by_distance else CUE_SECONDS

    cue_count = sum(1 for kind, _ in pieces if kind == "cue")

    used = 0.0

    built: list[WorkoutStep] = []

    for i, (kind, value) in enumerate(pieces):

        if kind == "cue":

            built.append(
                CueStep(
                    kind=step.kind, duration_sec=CUE_SECONDS,
                    pace_min=step.pace_min, pace_max=step.pace_max,
                    hr_min=step.hr_min, hr_max=step.hr_max, note=str(value),
                )
            )

            continue

        if i == last_run:

            size = max(
                100.0 if by_distance else 30.0, total - used - cue_count * cue_cost,
            )

        elif by_distance:

            size = max(100.0, round(float(value) * 60 * speed / 50) * 50)

        else:

            size = max(30.0, round(float(value) * 60 / 5) * 5)

        # metros e segundos INTEIROS (o relógio não precisa de 1561,538 m)
        size = float(round(size))

        used += size

        if by_distance:

            built.append(replace(step, distance_m=size, duration_sec=None))

        else:

            built.append(replace(step, duration_sec=int(size), distance_m=None))

    return built


def insert_fuel_cues(
    steps: list[WorkoutStep],
    times: list[int],
    optional: bool = False,
    no_gel: bool = False,
    session_pace: float | None = None,
) -> list[WorkoutStep]:
    """Os passos do treino com o aviso do gel nos minutos `times` (a partir do
    início). Sem horários ou sem como estimar, devolve os passos como vieram."""

    if not times or not steps:

        return list(steps)

    ordered = sorted(times)

    total = len(ordered)

    number = {t: i + 1 for i, t in enumerate(ordered)}

    pending = list(ordered)

    out: list[WorkoutStep] = []

    clock = 0.0

    for step in steps:

        if step.is_repeat:

            span = (step.reps or 1) * _span_minutes(step.steps, session_pace)

            out.append(step)

            clock += span

            # gel que cairia DENTRO dos tiros não mexe neles: descartado
            pending = [t for t in pending if t > clock]

            continue

        duration = _leaf_minutes(step, session_pace)

        if not duration:

            out.append(step)

            continue

        here = [t for t in pending if clock < t <= clock + duration]

        if not here:

            out.append(step)

            clock += duration

            continue

        pending = [t for t in pending if t not in here]

        cues = [
            (_clamp(t - clock, duration), _label(number[t], total, optional, no_gel))
            for t in here
        ]

        out.extend(_split(step, duration, cues, session_pace))

        clock += duration

    return out
