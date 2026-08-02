from datetime import datetime

from app.application.history.pace_model_builder import PaceModelBuilder
from app.domain.entities.activity import Activity
from app.domain.entities.pace_model import (
    SOURCE_DECLARED,
    SOURCE_ROOKIE,
    SOURCE_VDOT,
)
from app.domain.entities.training_history import TrainingHistory


def _run(distance_km: float, pace_min_km: float, sport: str = "Run") -> Activity:
    """Corrida sintética a um pace dado. average_speed em m/s; moving_time
    coerente com distância/pace."""

    speed = 1000 / (pace_min_km * 60)  # m/s

    distance_m = distance_km * 1000

    moving = int(distance_m / speed)

    return Activity(
        id=int(distance_km * 1000 + pace_min_km * 100),
        name="run",
        sport=sport,
        start_date=datetime(2026, 8, 1),
        timezone="America/Sao_Paulo",
        distance=distance_m,
        moving_time=moving,
        elapsed_time=moving,
        average_speed=speed,
        max_speed=speed,
        average_heartrate=150.0,
        max_heartrate=170.0,
        elevation_gain=0.0,
        elevation_high=None,
        elevation_low=None,
        start_latitude=None,
        start_longitude=None,
        end_latitude=None,
        end_longitude=None,
        kudos=0,
        comments=0,
        suffer_score=None,
        raw={},
    )


def _history(*runs: Activity) -> TrainingHistory:

    return TrainingHistory(activities=list(runs))


def _pace_str(p: float) -> str:

    m = int(p)
    s = round((p - m) * 60)

    if s == 60:
        m += 1
        s = 0

    return f"{m}:{s:02d}"


def test_vdot_anchored_on_best_real_effort():
    """10 km em 50:00 (VDOT ~40) entre rodagens fáceis -> limiar ~5:06,
    intervalado ~4:41 (bate com Daniels). Ancorado no que ele FEZ."""

    history = _history(
        _run(10, 5.0),     # o melhor esforço real (50 min nos 10k)
        _run(8, 6.1),
        _run(6, 6.2),
    )

    model = PaceModelBuilder.build(history)

    assert model.source == SOURCE_VDOT
    assert model.vdot is not None
    assert 39 <= model.vdot <= 41
    assert _pace_str(model.threshold) == "5:05"
    assert _pace_str(model.interval) == "4:41"


def test_condition_guard_caps_easy_to_real_easy_pace():
    """Um tiro forte (5 km a 4:24) puxaria o fácil pra ~5:40, MAS as rodagens
    reais dele são 6:10 — a trava segura o fácil perto do que ele sustenta.
    A regra do Renato: não mandar um pace que ele não aguenta."""

    history = _history(
        _run(5, 4.4),      # esforço forte -> VDOT alto
        _run(8, 6.17),     # rodagens leves REAIS ~6:10
        _run(9, 6.17),
        _run(7, 6.17),
    )

    model = PaceModelBuilder.build(history)

    assert model.easy_capped is True

    # fácil segurado perto do leve real (~6:00+), nunca no 5:40 do VDOT
    assert model.easy_min >= 5.9


def test_no_cap_when_athlete_already_runs_easy_fast_enough():
    """Quando as rodagens reais são MAIS rápidas que o fácil do VDOT, não há
    o que travar — o modelo só desacelera o atleta (não é risco de matar)."""

    history = _history(
        _run(10, 5.0),
        _run(8, 5.3),
        _run(6, 5.3),
    )

    model = PaceModelBuilder.build(history)

    assert model.easy_capped is False


def test_fallback_to_declared_pace_without_real_runs():
    """Sem corrida real utilizável -> modelo conservador do pace declarado."""

    class _Runner:
        initial_pace_min_km = 7.0

    model = PaceModelBuilder.build(_history(), _Runner())

    assert model.source == SOURCE_DECLARED
    assert model.vdot is None
    assert model.easy_min == 7.0


def test_fallback_to_rookie_without_anything():

    model = PaceModelBuilder.build(_history(), None)

    assert model.source == SOURCE_ROOKIE
    assert model.easy_min == 8.0


def test_walks_do_not_anchor_the_model():
    """Caminhada não é corrida — não vira âncora de VDOT."""

    model = PaceModelBuilder.build(_history(_run(5, 8.5, sport="Walk")), None)

    assert model.source == SOURCE_ROOKIE
