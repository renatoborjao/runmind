from app.application.history.hr_zone_calculator import HrZoneCalculator


def test_zone_minutes_splits_by_pct_max():
    """FCmáx 180. Metade a 99 bpm (55% -> Z1), metade a 170 bpm (94% -> Z5),
    60 min em movimento -> 30 min em Z1 e 30 em Z5."""

    heartrate = [99] * 100 + [170] * 100

    zones = HrZoneCalculator.zone_minutes(heartrate, 3600, max_hr=180)

    assert zones[0] == 30.0     # Z1
    assert zones[4] == 30.0     # Z5
    assert zones[1] == zones[2] == zones[3] == 0.0


def test_below_50pct_is_ignored():
    """FC abaixo de 50% da FCmáx (repouso/deriva) não entra em zona nenhuma."""

    heartrate = [80] * 100 + [170] * 100   # 80/180=44% -> fora

    zones = HrZoneCalculator.zone_minutes(heartrate, 3600, max_hr=180)

    # só a metade em Z5 conta; a soma das zonas < tempo total
    assert zones[4] == 30.0
    assert sum(zones) == 30.0


def test_edwards_load_weights_zones():
    """Carga = Σ min×peso. 30 em Z1 (×1) + 30 em Z5 (×5) = 180."""

    assert HrZoneCalculator.edwards_load([30, 0, 0, 0, 30]) == 180.0


def test_edwards_rewards_intensity_distribution():
    """Mesmo tempo total, mas mais tempo em zona alta = carga maior — o ponto
    de Edwards sobre a FC média."""

    easy = HrZoneCalculator.edwards_load([0, 40, 0, 0, 0])    # 40min Z2
    hard = HrZoneCalculator.edwards_load([0, 0, 0, 0, 40])    # 40min Z5

    assert hard > easy
    assert easy == 80.0 and hard == 200.0


def test_none_without_max_hr():

    assert HrZoneCalculator.zone_minutes([150] * 100, 3600, max_hr=None) is None


def test_none_for_short_stream():

    assert HrZoneCalculator.zone_minutes([150] * 5, 3600, max_hr=180) is None


def test_none_without_moving_time():

    assert HrZoneCalculator.zone_minutes([150] * 100, 0, max_hr=180) is None


def test_edwards_load_none_without_zones():

    assert HrZoneCalculator.edwards_load(None) is None
    assert HrZoneCalculator.edwards_load([1, 2, 3]) is None
