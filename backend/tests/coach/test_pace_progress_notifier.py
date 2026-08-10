from unittest.mock import MagicMock, patch

from app.application.coach.intelligence.pace_progress_notifier import (
    PaceProgressNotifier,
)
from app.domain.entities.pace_model import SOURCE_VDOT, PaceModel
from app.domain.entities.training_history import TrainingHistory

MODULE = "app.application.coach.intelligence.pace_progress_notifier"


def _model(vdot, easy_min=5.9) -> PaceModel:

    return PaceModel(
        easy_min=easy_min, easy_max=easy_min + 0.7, marathon=5.3, threshold=5.0,
        interval=4.6, rep=4.4, vdot=vdot, source=SOURCE_VDOT,
    )


def _runner():

    r = MagicMock()
    r.name = "Renato"
    return r


def _run(model_vdot, last_vdot, last_easy=None, model_easy=5.9):

    store = MagicMock()
    store.last_vdot.return_value = last_vdot
    store.last_easy_min.return_value = last_easy

    with (
        patch(f"{MODULE}.PaceModelBuilder") as builder,
        patch(f"{MODULE}.PaceProgressStore", return_value=store),
    ):

        builder.build.return_value = _model(model_vdot, model_easy)

        msg = PaceProgressNotifier.check(
            "renato", _runner(), TrainingHistory(activities=[]),
        )

    return msg, store


def test_first_time_sets_baseline_without_notifying():

    msg, store = _run(model_vdot=34.0, last_vdot=None, model_easy=6.0)

    assert msg is None
    store.save.assert_called_once_with("renato", 34.0, 6.0)


def test_meaningful_vdot_gain_notifies_full_reanchor():

    msg, store = _run(
        model_vdot=36.0, last_vdot=34.0, last_easy=6.2, model_easy=5.9,
    )

    assert msg is not None
    assert "mais rápido" in msg
    assert "Limiar" in msg  # reancoragem completa
    # watermark do fácil preservado (min entre atual e último)
    store.save.assert_called_once_with("renato", 36.0, 5.9)


def test_small_vdot_gain_flat_easy_does_not_notify():

    msg, store = _run(
        model_vdot=34.5, last_vdot=34.0, last_easy=5.9, model_easy=5.9,
    )

    assert msg is None
    store.save.assert_not_called()


def test_easy_improved_with_flat_vdot_notifies_easy_only():
    """O gap fechado: fácil evoluiu pela âncora de realidade, VDOT estável."""

    msg, store = _run(
        model_vdot=34.0, last_vdot=34.0, last_easy=6.1, model_easy=5.9,
    )

    assert msg is not None
    assert "fácil ficou mais rápido" in msg
    assert "Limiar" not in msg  # aviso focado no fácil, não reancoragem
    store.save.assert_called_once_with("renato", 34.0, 5.9)


def test_tiny_easy_improvement_does_not_notify():

    msg, store = _run(
        model_vdot=34.0, last_vdot=34.0, last_easy=6.0, model_easy=5.9,
    )

    assert msg is None
    store.save.assert_not_called()


def test_slower_easy_never_notifies():
    """Fácil ficou mais LENTO (oscilação/semana leve) → nunca vira aviso, e o
    watermark não recua."""

    msg, store = _run(
        model_vdot=34.0, last_vdot=34.0, last_easy=5.9, model_easy=6.3,
    )

    assert msg is None
    store.save.assert_not_called()


def test_legacy_file_without_easy_marker_bases_it_silently():
    """Arquivo antigo (só last_vdot): grava a base do fácil sem avisar."""

    msg, store = _run(
        model_vdot=34.0, last_vdot=34.0, last_easy=None, model_easy=5.9,
    )

    assert msg is None
    store.save.assert_called_once_with("renato", 34.0, 5.9)


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
