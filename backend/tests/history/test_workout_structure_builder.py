from app.application.history.workout_structure_builder import (
    WorkoutStructureBuilder,
)
from tests.coach.factories import make_activity


def _speed_from_pace(pace_min_km: float) -> float:
    """m/s a partir do pace min/km (o Strava manda average_speed)."""

    return 1000 / (pace_min_km * 60)


def _splits(paces: list[float]) -> list[dict]:

    return [
        {"distance": 1000, "average_speed": _speed_from_pace(p)}
        for p in paces
    ]


def _laps(paces: list[float], distance: float = 400) -> list[dict]:

    return [
        {"distance": distance, "average_speed": _speed_from_pace(p)}
        for p in paces
    ]


def _build(raw: dict):

    return WorkoutStructureBuilder.build(make_activity(raw=raw))


def test_no_detail_never_breaks():

    structure = _build({})

    assert structure.has_detail is False
    assert structure.km_splits == []
    assert structure.is_interval is False
    assert structure.split_trend == "unknown"


def test_steady_easy_run_is_not_interval():

    structure = _build({"splits_metric": _splits([6.0, 6.05, 5.95, 6.0])})

    assert structure.has_detail is True
    assert structure.is_interval is False
    assert structure.split_trend == "even"


def test_interval_detected_from_km_spread():

    # tiros: km rápidos (4:00) alternando com trote (6:30)
    structure = _build(
        {"splits_metric": _splits([4.0, 6.5, 4.0, 6.5, 4.0])}
    )

    assert structure.is_interval is True
    assert structure.fastest_km_pace == 4.0
    assert structure.slowest_km_pace == 6.5


def test_interval_detected_from_manual_laps():

    raw = {
        # kms suaves escondem o tiro; as voltas manuais entregam
        "splits_metric": _splits([5.5, 5.4, 5.6]),
        "laps": _laps([3.8, 6.5, 3.9, 6.4, 3.8, 6.6]),
    }

    structure = _build(raw)

    assert structure.lap_count == 6
    assert structure.is_interval is True


def test_negative_split_trend():

    structure = _build(
        {"splits_metric": _splits([6.2, 6.1, 5.6, 5.5])}
    )

    assert structure.split_trend == "negative"


def test_positive_split_trend():

    # queda acentuada: 2ª metade ~12.6% mais lenta -> quebra de verdade
    structure = _build(
        {"splits_metric": _splits([5.5, 5.6, 6.2, 6.3])}
    )

    assert structure.split_trend == "positive"


def test_mild_fade_is_not_a_break():
    """Bug do Renato: 2ª metade ~4% mais lenta virava "positive" e a IA
    dizia que ele QUEBROU. Diferença pequena é variação normal."""

    structure = _build(
        {"splits_metric": _splits([5.5, 5.5, 5.7, 5.75])}
    )

    assert structure.split_trend == "positive_mild"


def test_short_laps_are_ignored():

    raw = {"laps": _laps([4.0, 6.5, 4.0, 6.5], distance=150)}

    structure = _build(raw)

    # nenhuma volta >= 300 m: não conta como estrutura de voltas
    assert structure.lap_count == 0


def test_partial_final_split_is_dropped():

    raw = {
        "splits_metric": [
            {"distance": 1000, "average_speed": _speed_from_pace(6.0)},
            {"distance": 1000, "average_speed": _speed_from_pace(6.1)},
            # pedaço parcial final (196 m caminhando) — não é parcial real
            {"distance": 196, "average_speed": _speed_from_pace(32.0)},
        ]
    }

    structure = _build(raw)

    assert structure.km_splits == [6.0, 6.1]


def test_walk_pause_with_zero_speed_is_skipped():

    raw = {
        "splits_metric": [
            {"distance": 1000, "average_speed": _speed_from_pace(6.0)},
            {"distance": 1000, "average_speed": 0},
            {"distance": 1000, "average_speed": _speed_from_pace(6.0)},
        ]
    }

    structure = _build(raw)

    assert structure.km_splits == [6.0, 6.0]


def test_km_hr_is_captured_aligned_to_splits():

    raw = {
        "splits_metric": [
            {"distance": 1000, "average_speed": _speed_from_pace(5.0),
             "average_heartrate": 158.4},
            {"distance": 1000, "average_speed": _speed_from_pace(5.0),
             "average_heartrate": 165.7},
        ]
    }

    structure = _build(raw)

    assert structure.km_hr == [158, 166]


def test_cadence_is_doubled_to_steps_per_minute():

    structure = _build(
        {
            "splits_metric": _splits([6.0, 6.0]),
            "average_cadence": 85.0,
        }
    )

    assert structure.cadence_spm == 170


def test_cadence_falls_back_to_stream_when_summary_missing():

    # esteira sem average_cadence no resumo, mas com stream de cadência
    structure = _build(
        {
            "splits_metric": _splits([6.0, 6.0]),
            "_streams": {"cadence": [86, 88, 0, 90, None, 88]},
        }
    )

    # média dos válidos (86,88,90,88)=88 -> x2 = 176 passos/min
    assert structure.cadence_spm == 176
