from datetime import datetime
from unittest.mock import patch

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


class _RunnerWithId:
    id = "renato"
    initial_pace_min_km = None


_STORE = "app.infrastructure.persistence.best_effort_vdot_store.BestEffortVdotStore"


def test_best_effort_floor_raises_the_anchor():
    """Quando o VDOT do esforço CONTÍNUO (best_efforts) é maior que o da média
    da corrida, ele ancora — captura o teto que a média dilui."""

    history = _history(_run(10, 6.0), _run(8, 6.1), _run(6, 6.2))

    with patch(_STORE) as store:

        store.return_value.max_vdot.return_value = 42.0

        model = PaceModelBuilder.build(history, _RunnerWithId())

    assert model.vdot == 42.0


def test_best_effort_floor_never_lowers_the_anchor():
    """Um best-effort MENOR que a média nunca rebaixa o VDOT."""

    history = _history(_run(10, 5.0), _run(8, 5.2), _run(6, 5.1))

    with patch(_STORE) as store:

        store.return_value.max_vdot.return_value = 30.0

        model = PaceModelBuilder.build(history, _RunnerWithId())

    assert model.vdot > 30.0


def test_walks_do_not_anchor_the_model():
    """Caminhada não é corrida — não vira âncora de VDOT."""

    model = PaceModelBuilder.build(_history(_run(5, 8.5, sport="Walk")), None)

    assert model.source == SOURCE_ROOKIE


def test_gps_broken_run_does_not_anchor_capacity():
    """Hélio 27/09: UMA corrida com pico de 100,9 km/h (salto de GPS) saiu
    '7,6 km a 4:49' — ele roda 6:15-6:50 — e virava VDOT 41 (limiar 4:07).
    Pico sobre-humano = GPS quebrado: não ancora."""

    glitch = _run(7.6, 4.8)

    glitch.max_speed = 100.9 / 3.6

    history = _history(glitch, _run(7, 6.3), _run(10, 6.4), _run(6, 6.5))

    model = PaceModelBuilder.build(history)

    assert model.vdot < 32
    assert _pace_str(model.threshold) > "5:30"


def test_gps_broken_flags_only_superhuman_peaks():

    from app.application.history.pace_model_builder import gps_broken

    sprint = _run(5, 4.0)

    sprint.max_speed = 26 / 3.6  # tiro forte de gente

    glitch = _run(5, 4.0)

    glitch.max_speed = 60 / 3.6

    assert gps_broken(sprint) is False
    assert gps_broken(glitch) is True


# --- leve pela FC (nº 76) ----------------------------------------------------------------------


class _Runner:

    id = "leonardo"


def _recent_run(km: float, pace: float, days_ago: int, hr: float, trainer: bool = False):

    from datetime import timedelta

    run = _run(km, pace)

    run.start_date = datetime.now() - timedelta(days=days_ago)
    run.average_heartrate = hr
    run.raw = {"trainer": True} if trainer else {}
    run.id = int(days_ago * 1000 + pace * 100)

    return run


def _with_ceiling(ceiling: int | None):

    return (
        patch("app.application.history.hr_zone_resolver.HrZoneResolver.for_profile",
              return_value=object()),
        patch("app.application.history.training_patterns.TrainingPatterns.ceiling_of",
              return_value=ceiling),
    )


def _leonardo_history(extra=()):
    """10 km "de referência" a 6:42 com FC 149 (leve, não esforço máximo) + rodagens reais a
    ~6:50 com FC 135-142 — o fácil do modelo saía 7:07-7:34."""

    return _history(
        _recent_run(10, 6.7, 33, 149),
        _recent_run(5, 6.85, 22, 136),
        _recent_run(5.2, 6.6, 18, 140),
        _recent_run(5.1, 6.78, 14, 136),
        _recent_run(9, 6.88, 8, 142),
        _recent_run(8, 6.92, 2, 140),
        *extra,
    )


def test_the_easy_pace_follows_the_runs_done_inside_the_heart_rate_ceiling():
    """A régua do leve é a FC: se ele corre 6:50 com FC de leve, o fácil NÃO pode ser 7:07 só
    porque o VDOT vem de um esforço submáximo."""

    history = _leonardo_history()

    without = PaceModelBuilder.build(history)

    a, b = _with_ceiling(152)

    with a, b:

        with_hr = PaceModelBuilder.build(history, _Runner())

    assert with_hr.easy_min < without.easy_min
    assert with_hr.easy_min <= 6.9
    # só a ponta rápida se mexe: o resto do modelo (limiar, VO2) segue a fisiologia
    assert with_hr.threshold == without.threshold and with_hr.interval == without.interval


def test_runs_above_the_ceiling_or_on_the_treadmill_do_not_confirm_an_easy_pace():

    a, b = _with_ceiling(152)

    quality = _leonardo_history(extra=(_recent_run(8, 6.0, 5, 165), _recent_run(8, 6.05, 6, 168)))

    with a, b:

        assert PaceModelBuilder._hr_confirmed_easy_paces(quality, _Runner()) == (
            PaceModelBuilder._hr_confirmed_easy_paces(_leonardo_history(), _Runner())
        )

        # esteira: pace estimado, não prova nada
        treadmill = _history(
            _recent_run(5, 5.5, 3, 130, trainer=True), _recent_run(5, 5.6, 4, 130, trainer=True),
            _recent_run(5, 5.7, 5, 130, trainer=True),
        )

        assert PaceModelBuilder._hr_confirmed_easy_paces(treadmill, _Runner()) == []


def test_without_a_sample_or_a_heart_rate_ruler_the_model_is_what_it_was():

    history = _leonardo_history()

    baseline = PaceModelBuilder.build(history)

    # sem régua de FC (sem repouso): nada muda
    a, b = _with_ceiling(None)

    with a, b:

        assert PaceModelBuilder.build(history, _Runner()).easy_min == baseline.easy_min

    # sem atleta (sem como achar a régua): nada muda
    assert PaceModelBuilder.build(history).easy_min == baseline.easy_min

    # menos de 3 corridas dentro do teto: nada muda
    few = _history(_recent_run(10, 6.7, 33, 149), _recent_run(5, 6.8, 10, 140))

    a, b = _with_ceiling(152)

    with a, b:

        assert (
            PaceModelBuilder.build(few, _Runner()).easy_min
            == PaceModelBuilder.build(few).easy_min
        )


def test_the_heart_rate_evidence_never_slows_an_athlete_who_already_runs_easy_faster():
    """Só acelera a ponta rápida: quem faz o leve mais rápido que a evidência segue como estava."""

    fast = _history(
        _recent_run(10, 5.0, 33, 150),
        _recent_run(8, 5.3, 20, 140), _recent_run(6, 5.3, 12, 140), _recent_run(6, 5.35, 5, 141),
    )

    baseline = PaceModelBuilder.build(fast)

    a, b = _with_ceiling(152)

    with a, b:

        assert PaceModelBuilder.build(fast, _Runner()).easy_min <= baseline.easy_min
