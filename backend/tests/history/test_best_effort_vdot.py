from app.application.history.best_effort_vdot import BestEffortVdot
from app.application.history.vdot_calculator import VdotCalculator


def _e(name, dist, secs):

    return {"name": name, "distance": dist, "elapsed_time": secs}


def test_uses_best_sustained_effort_not_the_sprint():
    """Um 400m absurdamente rápido NÃO ancora (anaeróbico, superestima); o VDOT
    sai do esforço sustentado (5K)."""

    efforts = [
        _e("400m", 400, 60),        # 2:30/km — se contasse, VDOT gigante
        _e("5K", 5000, 1500),       # 5:00/km — o sustentado real
    ]

    vdot = BestEffortVdot.from_efforts(efforts)

    # bate com o VDOT do 5K, não com o do 400m
    assert abs(vdot - VdotCalculator.vdot(5000, 1500)) < 0.01


def test_falls_back_to_one_mile_without_3k():

    efforts = [_e("400m", 400, 70), _e("1 mile", 1609, 360)]

    vdot = BestEffortVdot.from_efforts(efforts)

    assert abs(vdot - VdotCalculator.vdot(1609, 360)) < 0.01


def test_none_without_usable_efforts():

    assert BestEffortVdot.from_efforts([]) is None
    assert BestEffortVdot.from_efforts([_e("400m", 400, 70)]) is None


def test_picks_the_highest_vdot_among_sustained():
    """Entre os sustentados, pega o maior VDOT (o esforço mais forte)."""

    efforts = [
        _e("5K", 5000, 1500),       # 5:00/km
        _e("2 mile", 3219, 900),    # ~4:40/km — mais forte
    ]

    vdot = BestEffortVdot.from_efforts(efforts)

    assert abs(vdot - VdotCalculator.vdot(3219, 900)) < 0.01
