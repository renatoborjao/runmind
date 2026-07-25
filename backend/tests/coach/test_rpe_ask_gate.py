from types import SimpleNamespace

from app.application.events.training_completed import TrainingCompletedEvent


def _result(planned_type=None, detected_type=None):

    planned = (
        SimpleNamespace(workout_type=planned_type)
        if planned_type is not None
        else None
    )

    enriched = SimpleNamespace(training_type=detected_type)

    return {"planned_session": planned, "activity": enriched}


def test_demanding_by_planned_label():

    assert TrainingCompletedEvent._is_demanding(_result(planned_type="Velocidade 9km"))
    assert TrainingCompletedEvent._is_demanding(_result(planned_type="Longão Progressivo"))
    assert TrainingCompletedEvent._is_demanding(_result(planned_type="Treino de Limiar"))
    assert TrainingCompletedEvent._is_demanding(_result(planned_type="Tiros 5x800"))


def test_demanding_by_detected_type_english():
    """O tipo detectado vem do WorkoutType (inglês)."""

    assert TrainingCompletedEvent._is_demanding(_result(detected_type="INTERVAL"))
    assert TrainingCompletedEvent._is_demanding(_result(detected_type="THRESHOLD"))
    assert TrainingCompletedEvent._is_demanding(_result(detected_type="LONG_RUN"))
    assert TrainingCompletedEvent._is_demanding(_result(detected_type="VO2"))
    assert TrainingCompletedEvent._is_demanding(_result(detected_type="RACE"))


def test_easy_runs_are_not_demanding():

    assert not TrainingCompletedEvent._is_demanding(
        _result(planned_type="Rodagem leve", detected_type="EASY")
    )
    assert not TrainingCompletedEvent._is_demanding(
        _result(detected_type="RECOVERY")
    )
    assert not TrainingCompletedEvent._is_demanding(
        _result(planned_type="Rodagem 8km", detected_type="UNKNOWN")
    )


def test_no_labels_is_not_demanding():

    assert not TrainingCompletedEvent._is_demanding({"planned_session": None, "activity": None})
