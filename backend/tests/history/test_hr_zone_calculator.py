from app.application.history.hr_zone_calculator import HrZoneCalculator


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
