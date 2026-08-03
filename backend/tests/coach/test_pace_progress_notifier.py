from unittest.mock import MagicMock, patch

from app.application.coach.intelligence.pace_progress_notifier import (
    PaceProgressNotifier,
)
from app.domain.entities.pace_model import SOURCE_VDOT, PaceModel
from app.domain.entities.training_history import TrainingHistory

MODULE = "app.application.coach.intelligence.pace_progress_notifier"


def _model(vdot) -> PaceModel:

    return PaceModel(
        easy_min=5.9, easy_max=6.6, marathon=5.3, threshold=5.0,
        interval=4.6, rep=4.4, vdot=vdot, source=SOURCE_VDOT,
    )


def _runner():

    r = MagicMock()
    r.name = "Renato"
    return r


def _run(model_vdot, last_vdot):

    store = MagicMock()
    store.last_vdot.return_value = last_vdot

    with (
        patch(f"{MODULE}.PaceModelBuilder") as builder,
        patch(f"{MODULE}.PaceProgressStore", return_value=store),
    ):

        builder.build.return_value = _model(model_vdot)

        msg = PaceProgressNotifier.check(
            "renato", _runner(), TrainingHistory(activities=[]),
        )

    return msg, store


def test_first_time_sets_baseline_without_notifying():

    msg, store = _run(model_vdot=34.0, last_vdot=None)

    assert msg is None
    store.save.assert_called_once_with("renato", 34.0)


def test_meaningful_gain_notifies_and_updates():

    msg, store = _run(model_vdot=36.0, last_vdot=34.0)

    assert msg is not None
    assert "mais rápido" in msg
    assert "Limiar" in msg
    store.save.assert_called_once_with("renato", 36.0)


def test_small_gain_does_not_notify():

    msg, store = _run(model_vdot=34.5, last_vdot=34.0)

    assert msg is None
    store.save.assert_not_called()


def test_no_vdot_returns_none():

    store = MagicMock()

    with (
        patch(f"{MODULE}.PaceModelBuilder") as builder,
        patch(f"{MODULE}.PaceProgressStore", return_value=store),
    ):

        builder.build.return_value = _model(None)

        msg = PaceProgressNotifier.check(
            "renato", _runner(), TrainingHistory(activities=[]),
        )

    assert msg is None
