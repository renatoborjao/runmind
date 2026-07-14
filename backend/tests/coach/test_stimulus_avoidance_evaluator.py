from app.application.coach.intelligence.stimulus_avoidance_evaluator import (
    StimulusAvoidanceEvaluator,
)
from tests.coach.factories import (
    make_enriched_activity,
    make_planned_session,
)


def _evaluate(planned_overrides, executed_overrides):

    planned = (
        make_planned_session(**planned_overrides)
        if planned_overrides is not None
        else None
    )

    executed = make_enriched_activity(**executed_overrides)

    return StimulusAvoidanceEvaluator.evaluate(planned, executed)


def test_speed_downgraded_to_easy_is_avoided():
    """Planejou intervalado, executou rodagem leve = fugiu do estímulo."""

    verdict = _evaluate(
        {"workout_type": "VO2"},
        {"training_type": "RODAGEM"},
    )

    assert verdict == ("SPEED", True)


def test_speed_done_as_speed_is_not_avoided():
    """Fez o tiro de verdade: nada a sinalizar (pace médio de tiro NÃO é
    usado — evita o falso positivo do aquecimento/recuperação)."""

    verdict = _evaluate(
        {"workout_type": "VO2", "target_pace_max": "4:00"},
        {"training_type": "VO2", "pace_min_km": 6.5},
    )

    assert verdict == ("SPEED", False)


def test_tempo_much_slower_than_target_is_avoided():
    """Ritmo contínuo bem mais devagar que o alvo = furou o pace."""

    verdict = _evaluate(
        {"workout_type": "TEMPO", "target_pace_max": "5:30"},
        {"training_type": "TEMPO", "pace_min_km": 6.2},
    )

    assert verdict == ("TEMPO", True)


def test_tempo_within_target_is_not_avoided():

    verdict = _evaluate(
        {"workout_type": "TEMPO", "target_pace_max": "5:30"},
        {"training_type": "TEMPO", "pace_min_km": 5.7},
    )

    assert verdict == ("TEMPO", False)


def test_easy_planned_is_not_a_quality_session():
    """Rodagem/leve não tem estímulo a 'evitar' -> fora do detector."""

    verdict = _evaluate(
        {"workout_type": "EASY"},
        {"training_type": "RODAGEM"},
    )

    assert verdict is None


def test_unplanned_extra_workout_is_ignored():

    verdict = _evaluate(
        None,
        {"training_type": "RODAGEM"},
    )

    assert verdict is None
