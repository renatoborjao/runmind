"""CALIBRAÇÃO DO PACE PELA EVOLUÇÃO — o modelo de ritmos não pode ser um freio.

O VDOT do atleta vem do MELHOR esforço real que ele já mostrou. Quem nunca correu forte
(Leonardo: um 10 km em 1:07 com FC de leve, VDOT ~31) fica ancorado num esforço SUBMÁXIMO:
limiar 6:16, VO2 5:46, enquanto o relógio dele projeta 10 km em 56:33, os tiros saem a 5:27
com esforço 3/10 e ele diz que as metas estão baixas. O modelo só subia se ele corresse uma
prova — o coach "braço de ferro", que segura o atleta que já evoluiu (Renato, 29/10: "atleta
está evoluindo, não tem que frear").

Aqui o VDOT acompanha a evidência: quando o histórico fica abaixo do que o relógio projeta
(Garmin, VO₂máx) E o atleta passa da faixa do plano nos fortes (mais rápido que a ponta
rápida, nos blocos medidos ou no relato dele), o VDOT sobe uma fração do caminho até o do
relógio — metade com duas sessões assim, mais a cada nova, até 90%. Nunca passa do relógio
(que costuma ser otimista: Maurício 52:38 projetado × 58:30 na prova) e nunca baixa o VDOT do
histórico. Sem folga demonstrada, nada muda. Puro/determinístico; a evidência vem do
`stimulus_delivery` (blocos do relógio ou relato dele)."""

import time
from dataclasses import dataclass
from datetime import date, timedelta

from app.application.history.stimulus_delivery import DELIVERED, Delivery
from app.application.history.vdot_calculator import VdotCalculator

# o relógio precisa estar pelo menos isto acima do histórico pra haver o que calibrar
GARMIN_GAP_MIN = 0.04

# janela da evidência e mínimo de fortes entregues "com folga" pra calibrar
EVIDENCE_WEEKS = 5
MIN_SLACK_SESSIONS = 2

# passar da ponta rápida da faixa por pelo menos isto (s/km) é a prova OBJETIVA de que o alvo está
# abaixo do que ele faz; e sem ter se matado pra isso (esforço relatado até aqui, se relatou).
# O esforço sozinho NÃO vale: tem atleta que dá ≤3/10 em tudo por hábito (Maurício, 21 de 22).
OVERSHOOT_S = 8
OVERSHOOT_MAX_RPE = 5

# uma prova (esforço MÁXIMO) nesta janela ancora o VDOT de verdade: o histórico já é a capacidade
# dele e o relógio é otimista (Maurício: Garmin 52:38 × prova 58:30) — não calibra
RACE_ANCHOR_DAYS = 180

# o pace é pedido várias vezes por requisição: lembra o resultado por este tempo (s)
_CACHE_SECONDS = 120

# fração do caminho até o VDOT do relógio: base com o mínimo de sessões, +STEP por sessão a mais,
# nunca além de MAX (o relógio é otimista)
BASE_WEIGHT = 0.5
STEP_WEIGHT = 0.1
MAX_WEIGHT = 0.9


@dataclass(slots=True, frozen=True)
class Calibration:

    vdot: float
    base_vdot: float
    garmin_vdot: float
    weight: float
    sessions: int


def garmin_vdot(prediction) -> float | None:
    """O VDOT que a projeção do relógio implica (média dos tempos de 5 km e 10 km que ele deu).
    None sem projeção."""

    if prediction is None or not getattr(prediction, "has_data", False):

        return None

    values = []

    for meters, seconds in (
        (5000, getattr(prediction, "time_5k_sec", None)),
        (10000, getattr(prediction, "time_10k_sec", None)),
    ):

        if seconds and seconds > 0:

            values.append(VdotCalculator.vdot(meters, seconds))

    return sum(values) / len(values) if values else None


def slack_sessions(items: list[Delivery], today: date) -> int:
    """Quantos fortes ele fez MAIS RÁPIDO que a faixa do plano (pelo menos `OVERSHOOT_S` s/km, nos
    blocos medidos do relógio ou no relato dele) sem se matar, nas últimas semanas."""

    since = today - timedelta(weeks=EVIDENCE_WEEKS)

    return sum(
        1 for item in items
        if item.verdict == DELIVERED and item.day >= since
        and item.gap_s is not None and item.gap_s <= -OVERSHOOT_S
        and (item.rpe is None or item.rpe <= OVERSHOOT_MAX_RPE)
    )


def calibrate(
    base_vdot: float | None,
    prediction,
    items: list[Delivery],
    today: date,
    recent_race: bool = False,
) -> Calibration | None:
    """O VDOT calibrado, ou None quando não há o que calibrar (sem relógio, relógio perto do
    histórico, prova recente que já ancora o VDOT, ou sem folga demonstrada)."""

    target = garmin_vdot(prediction)

    if base_vdot is None or target is None or recent_race:

        return None

    if target < base_vdot * (1 + GARMIN_GAP_MIN):

        return None

    sessions = slack_sessions(items, today)

    if sessions < MIN_SLACK_SESSIONS:

        return None

    weight = min(MAX_WEIGHT, BASE_WEIGHT + STEP_WEIGHT * (sessions - MIN_SLACK_SESSIONS))

    return Calibration(
        vdot=base_vdot + weight * (target - base_vdot),
        base_vdot=base_vdot,
        garmin_vdot=target,
        weight=weight,
        sessions=sessions,
    )


def recent_race(profile: str, today: date) -> bool:
    """Ele correu uma PROVA nos últimos `RACE_ANCHOR_DAYS` dias? Resultado registrado pelo coach OU
    atividade marcada como prova (o detector ignora os treinos do próprio coach com "prova" no
    nome)."""

    from app.application.history.race_detector import RaceDetector
    from app.infrastructure.persistence.activity_archive_repository import (
        ActivityArchiveRepository,
    )
    from app.infrastructure.persistence.race_result_repository import RaceResultRepository

    event = RaceDetector.most_recent(
        ActivityArchiveRepository().load_activities(profile),
        today,
        past_results=RaceResultRepository().load(profile),
        lookback_weeks=RACE_ANCHOR_DAYS // 7,
    )

    return event is not None


_CACHE: dict[tuple, tuple[float, Calibration | None]] = {}


def for_runner(base_vdot: float | None, runner, today: date | None = None) -> Calibration | None:
    """A calibração do atleta a partir dos dados salvos (relógio, fortes entregues, provas).
    Best-effort: qualquer falha = sem calibração (o modelo segue como era)."""

    profile = getattr(runner, "id", None) if runner else None

    if not profile or base_vdot is None:

        return None

    try:

        from app.application.history import stimulus_delivery
        from app.core.clock import today_local
        from app.infrastructure.persistence.race_prediction_repository import (
            RacePredictionRepository,
        )

        today = today or today_local()

        key = (profile, today, round(base_vdot, 2))

        hit = _CACHE.get(key)

        if hit and time.monotonic() - hit[0] < _CACHE_SECONDS:

            return hit[1]

        summary = stimulus_delivery.for_profile(profile, today)

        result = calibrate(
            base_vdot,
            RacePredictionRepository().load(profile),
            summary.items if summary else [],
            today,
            recent_race(profile, today),
        )

        _CACHE[key] = (time.monotonic(), result)

        return result

    except Exception as e:  # noqa: BLE001

        print(f"Calibração do pace falhou p/ '{profile}': {e}")

        return None


def note(calibration: Calibration) -> str:
    """A frase pro dossiê: de onde vieram os ritmos (pro coach e pro atleta não acharem que o
    pace subiu do nada)."""

    return (
        f"Ritmos CALIBRADOS pela evolução dele: o histórico sozinho dava VDOT "
        f"{calibration.base_vdot:.0f}, o relógio projeta {calibration.garmin_vdot:.0f} e ele "
        f"fez {calibration.sessions} fortes MAIS RÁPIDO que a faixa do plano — "
        f"os ritmos usam {calibration.weight:.0%} do caminho até o relógio "
        f"(VDOT {calibration.vdot:.0f}) e sobem sozinhos se ele seguir entregando."
    )
