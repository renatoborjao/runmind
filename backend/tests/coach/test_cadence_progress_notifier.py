from datetime import date, datetime
from unittest.mock import MagicMock, patch

from app.application.coach.intelligence.cadence_progress_notifier import (
    CadenceProgressNotifier,
)
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_activity

MODULE = "app.application.coach.intelligence.cadence_progress_notifier"

_TODAY = date(2026, 8, 30)


def _runner():

    r = MagicMock()
    r.name = "Renato"
    return r


def _hist(spm: int, n: int = 3) -> TrainingHistory:
    """n corridas recentes com a cadência dada (raw guarda RPM por perna)."""

    acts = [
        make_activity(
            id=i,
            start_date=datetime(2026, 8, 20, 7, 0, 0),
            distance=8000.0,
            average_speed=3.33,  # ~5:00/km (ritmo de corrida)
            raw={"average_cadence": spm / 2},
        )
        for i in range(n)
    ]

    return TrainingHistory(activities=acts)


def _run(hist, saved, *, legacy=False):

    store = MagicMock()
    store.load.return_value = saved

    guard = MagicMock()
    guard.already_sent.return_value = legacy

    with (
        patch(f"{MODULE}.CadenceProgressStore", return_value=store),
        patch(f"{MODULE}.DispatchGuard", guard),
        patch(f"{MODULE}.today_local", return_value=_TODAY),
    ):

        msg = CadenceProgressNotifier.check("renato", _runner(), hist)

    return msg, store


def test_first_time_low_cadence_sends_initial_tip():

    msg, store = _run(_hist(158), saved=None)

    assert msg is not None
    assert "dica de forma" in msg
    assert "158" in msg
    _, kwargs = store.save.call_args
    assert kwargs["state"] == "watching"
    assert kwargs["baseline_spm"] == 158


def test_first_time_but_already_got_legacy_tip_seeds_silently():
    """Quem já recebeu a dica pelo gatilho antigo não leva a intro de novo —
    o loop engata em silêncio e passa a acompanhar."""

    msg, store = _run(_hist(158), saved=None, legacy=True)

    assert msg is None
    store.save.assert_called_once()
    _, kwargs = store.save.call_args
    assert kwargs["state"] == "watching"


def test_first_time_cadence_already_ok_says_nothing():

    msg, store = _run(_hist(168), saved=None)

    assert msg is None
    store.save.assert_not_called()


def test_hitting_target_celebrates_and_closes():

    saved = {
        "state": "watching",
        "baseline_spm": 160,
        "anchor_date": "2026-08-01",
        "re_nudged": False,
    }

    msg, store = _run(_hist(172), saved=saved)

    assert msg is not None
    assert "no ponto" in msg
    _, kwargs = store.save.call_args
    assert kwargs["state"] == "closed"


def test_sustained_progress_acknowledges_and_reanchors():

    saved = {
        "state": "watching",
        "baseline_spm": 158,
        "anchor_date": "2026-08-01",
        "re_nudged": False,
    }

    msg, store = _run(_hist(164), saved=saved)  # +6 desde a base

    assert msg is not None
    assert "subindo" in msg
    _, kwargs = store.save.call_args
    assert kwargs["state"] == "watching"
    assert kwargs["baseline_spm"] == 164  # re-ancora
    assert kwargs["re_nudged"] is False


def test_small_change_stays_silent():

    saved = {
        "state": "watching",
        "baseline_spm": 158,
        "anchor_date": "2026-08-20",  # recente, sem tempo de travar
        "re_nudged": False,
    }

    msg, store = _run(_hist(159), saved=saved)  # +1, ruído

    assert msg is None
    store.save.assert_not_called()


def test_stuck_for_weeks_gives_one_renudge_then_marks():

    saved = {
        "state": "watching",
        "baseline_spm": 158,
        "anchor_date": "2026-07-20",  # >28 dias antes de _TODAY
        "re_nudged": False,
    }

    msg, store = _run(_hist(159), saved=saved)

    assert msg is not None
    assert "Voltando na cadência" in msg
    _, kwargs = store.save.call_args
    assert kwargs["re_nudged"] is True


def test_stuck_but_already_renudged_stays_silent():

    saved = {
        "state": "watching",
        "baseline_spm": 158,
        "anchor_date": "2026-07-20",
        "re_nudged": True,
    }

    msg, store = _run(_hist(159), saved=saved)

    assert msg is None
    store.save.assert_not_called()


def test_closed_never_speaks_again():

    saved = {
        "state": "closed",
        "baseline_spm": 172,
        "anchor_date": "2026-08-01",
        "re_nudged": False,
    }

    msg, store = _run(_hist(158), saved=saved)

    assert msg is None
    store.save.assert_not_called()


def test_not_enough_samples_says_nothing():

    msg, store = _run(_hist(158, n=2), saved=None)  # < _MIN_SAMPLES

    assert msg is None
    store.save.assert_not_called()
