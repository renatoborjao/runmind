from app.application.history.activity_enricher import ActivityEnricher
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.value_objects.hr_zones import HrZones
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


def test_with_hr_without_zone_ruler_keeps_relative_intensity_but_no_zone():

    # sem régua de zonas (sem idade/FC máx) a intensidade é só relativa à FC
    # de costume — não é zona de FC, então não rotula "Zn"
    activity = make_activity(
        average_heartrate=150.0,
    )

    enriched = ActivityEnricher.enrich(activity, _metrics())

    assert enriched.intensity == "MEDIUM"
    assert enriched.estimated_zone == ""


def test_zone_comes_from_athlete_ruler_not_from_usual_hr():

    # caso real do Renato (25/09): rodagem leve a 144 bpm, zonas do relógio
    # (reserva de FC, máx 194/repouso 66). A FC de costume dele é ~153 — o
    # rótulo relativo dizia "Z2" por acaso e o gráfico (%FCmáx por idade)
    # dizia Z3/Z4. Agora os dois leem a MESMA régua: Z2.
    zones = HrZones(floors=(130, 143, 156, 168, 181), method="garmin")

    activity = make_activity(average_heartrate=144.0)

    enriched = ActivityEnricher.enrich(
        activity, _metrics(average_hr=153.0, hr_zones=zones)
    )

    assert enriched.estimated_zone == "Z2"
    assert enriched.intensity == "LOW"
    assert enriched.hr_zones is zones


def test_hard_effort_by_ruler_even_below_usual_hr():

    # atleta que corre tudo forte: FC de costume 170. Um treino a 165 seria
    # "abaixo da média" no relativo — na régua do atleta é Z4 (forte).
    zones = HrZones(floors=(130, 143, 156, 164, 181), method="hrr")

    enriched = ActivityEnricher.enrich(
        make_activity(average_heartrate=165.0),
        _metrics(average_hr=170.0, hr_zones=zones),
    )

    assert enriched.estimated_zone == "Z4"
    assert enriched.intensity == "HIGH"


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


def _split(pace_min_km: float) -> dict:

    return {"distance": 1000, "average_speed": 1000 / (pace_min_km * 60)}


def test_interval_splits_are_classified_as_interval():

    # tiros de 4:00 alternando com trote de 6:30: a média (~5:15) sozinha
    # viraria "rodagem", mas a estrutura dos splits entrega o intervalado
    activity = make_activity(
        distance=5000.0,
        moving_time=1575,
        average_heartrate=155.0,
        raw={
            "splits_metric": [
                _split(4.0),
                _split(6.5),
                _split(4.0),
                _split(6.5),
                _split(4.0),
            ],
        },
    )

    enriched = ActivityEnricher.enrich(activity, _metrics())

    assert enriched.structure.is_interval is True
    assert enriched.training_type == "INTERVAL"


def test_steady_run_without_structure_is_not_interval():

    activity = make_activity(
        distance=6000.0,
        average_heartrate=150.0,
        raw={
            "splits_metric": [
                _split(6.0),
                _split(6.05),
                _split(5.95),
            ],
        },
    )

    enriched = ActivityEnricher.enrich(activity, _metrics())

    assert enriched.training_type != "INTERVAL"


def test_zero_distance_activity_does_not_crash():

    # corrida sem distância (esteira/HIIT sem sensor): average_speed 0 daria
    # ZeroDivisionError no cálculo de pace — o guard mantém pace/eficiência 0
    # sem crashar (a entrada webhook/poller já pula essas atividades)
    activity = make_activity(
        distance=0.0,
        average_speed=0.0,
        average_heartrate=None,
        max_heartrate=None,
    )

    enriched = ActivityEnricher.enrich(activity, _metrics())

    assert enriched.pace_min_km == 0.0
    assert enriched.efficiency_score == 0.0


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


_WATCH = HrZones(floors=(130, 143, 156, 168, 181), method="garmin")


def _renato_metrics(**overrides) -> RunnerMetrics:

    # faixas reais do Renato (ordem de grandeza): leve 6:00–6:45, limiar ~5:05
    defaults = dict(
        easy_pace_min=6.00,
        easy_pace_max=6.75,
        threshold_pace=5.08,
        vo2_pace=4.60,
        average_hr=153.0,
        max_long_run=14.5,
        weekly_volume=28.0,
        hr_zones=_WATCH,
    )

    defaults.update(overrides)

    return RunnerMetrics(**defaults)


def test_easy_run_in_target_is_easy_not_tempo():
    """Bug 25/09: 8,5 km em 54 min a 6:23 (alvo 6:20–6:45), FC 144 (Z2 no
    relógio) saiu 'Tipo identificado: Ritmo' porque distância e duração
    pontuavam como ritmo. Intensidade decide: é rodagem."""

    activity = make_activity(
        distance=8530.0,
        moving_time=3268,
        average_speed=8530.0 / 3268,
        average_heartrate=144.0,
    )

    enriched = ActivityEnricher.enrich(activity, _renato_metrics())

    assert enriched.training_type == "EASY"


def test_threshold_pace_with_z4_hr_is_tempo():

    activity = make_activity(
        distance=8000.0,
        moving_time=8 * 5.0 * 60,
        average_speed=8000.0 / (8 * 5.0 * 60),
        average_heartrate=165.0,
    )

    enriched = ActivityEnricher.enrich(activity, _renato_metrics())

    assert enriched.training_type == "TEMPO"


def test_slow_z1_run_is_recovery():

    activity = make_activity(
        distance=5000.0,
        moving_time=5 * 7.2 * 60,
        average_speed=5000.0 / (5 * 7.2 * 60),
        average_heartrate=128.0,
    )

    enriched = ActivityEnricher.enrich(activity, _renato_metrics())

    assert enriched.training_type == "RECOVERY"


def test_long_distance_easy_is_long_run():

    activity = make_activity(
        distance=14000.0,
        moving_time=14 * 6.4 * 60,
        average_speed=14000.0 / (14 * 6.4 * 60),
        average_heartrate=147.0,
    )

    enriched = ActivityEnricher.enrich(activity, _renato_metrics())

    assert enriched.training_type == "LONG_RUN"


def test_duration_alone_never_makes_tempo():
    """Rodar muito tempo leve (70 min, abaixo do longão) segue rodagem."""

    activity = make_activity(
        distance=9500.0,
        moving_time=int(9.5 * 6.5 * 60),
        average_speed=9500.0 / (9.5 * 6.5 * 60),
        average_heartrate=146.0,
    )

    enriched = ActivityEnricher.enrich(activity, _renato_metrics())

    assert enriched.training_type == "EASY"
