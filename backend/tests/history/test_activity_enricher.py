from app.application.history.activity_enricher import ActivityEnricher
from app.domain.entities.runner_metrics import RunnerMetrics
from tests.coach.factories import make_activity


def _metrics(**overrides) -> RunnerMetrics:

    defaults = dict(
        easy_pace_min=5.20,
        easy_pace_max=5.80,
        threshold_pace=4.85,
        vo2_pace=4.35,
        average_hr=150.0,
        max_long_run=15.0,
        weekly_volume=30.0,
    )

    defaults.update(overrides)

    return RunnerMetrics(**defaults)


def test_without_hr_slow_pace_is_very_low_not_medium():

    # trote de ~121 min/km sem FC: antes virava MEDIUM/Z3 porque a FC
    # média era emprestada; agora a intensidade vem do pace
    activity = make_activity(
        distance=100.0,
        moving_time=730,
        average_speed=0.137,
        average_heartrate=None,
        max_heartrate=None,
    )

    enriched = ActivityEnricher.enrich(activity, _metrics())

    assert enriched.intensity == "VERY_LOW"
    assert enriched.estimated_zone == "Z1"


def test_without_hr_fast_pace_is_very_high():

    # pace de VO2 (4:20 min/km) sem FC
    activity = make_activity(
        distance=5000.0,
        moving_time=1300,
        average_speed=3.85,
        average_heartrate=None,
        max_heartrate=None,
    )

    enriched = ActivityEnricher.enrich(activity, _metrics())

    assert enriched.intensity == "VERY_HIGH"
    assert enriched.estimated_zone == "Z5"


def test_with_hr_keeps_hr_based_intensity():

    activity = make_activity(
        average_heartrate=150.0,
    )

    enriched = ActivityEnricher.enrich(activity, _metrics())

    assert enriched.intensity == "MEDIUM"
    assert enriched.estimated_zone == "Z3"


def test_below_10km_is_never_long_run_even_with_long_duration():

    # 8 km em 100 min: duração de longão, mas abaixo do piso de 10 km
    activity = make_activity(
        distance=8000.0,
        moving_time=6000,
        average_speed=1.33,
        average_heartrate=None,
    )

    enriched = ActivityEnricher.enrich(
        activity,
        _metrics(max_long_run=8.0),
    )

    assert enriched.training_type != "LONG_RUN"


def test_10km_or_more_can_be_long_run():

    # 12 km em ~95 min, perto do longão máximo do corredor
    activity = make_activity(
        distance=12000.0,
        moving_time=5700,
        average_speed=2.10,
        average_heartrate=None,
    )

    enriched = ActivityEnricher.enrich(
        activity,
        _metrics(max_long_run=13.0),
    )

    assert enriched.training_type == "LONG_RUN"


def test_tiny_activity_is_never_classified_as_long_run():

    # histórico minúsculo: max_long_run de 100 m fazia 100 m virar
    # "distância típica de longão"
    activity = make_activity(
        distance=100.0,
        moving_time=730,
        average_speed=0.137,
        average_heartrate=None,
    )

    enriched = ActivityEnricher.enrich(
        activity,
        _metrics(max_long_run=0.1),
    )

    assert enriched.training_type != "LONG_RUN"
