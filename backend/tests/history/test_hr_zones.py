from dataclasses import dataclass
from types import SimpleNamespace

from app.application.history.hr_zone_resolver import HrZoneResolver
from app.domain.value_objects.hr_zones import (
    HrZones,
    dominant_zone,
    zone_share_label,
)


def test_hrr_matches_garmin_watch_zones():
    """Reserva de FC 50/60/70/80/90% = padrão do Garmin. Máx 194 / repouso 66
    (o relógio do Renato) reproduz os pisos que o Garmin devolveu."""

    zones = HrZones.from_hrr(194, 66)

    assert zones.floors == (130, 143, 156, 168, 181)


def test_zone_of_uses_floors():

    zones = HrZones(floors=(130, 143, 156, 168, 181), method="garmin")

    assert zones.zone_of(129) is None       # abaixo de Z1
    assert zones.zone_of(130) == 1
    assert zones.zone_of(144) == 2
    assert zones.zone_of(155) == 2
    assert zones.zone_of(156) == 3
    assert zones.zone_of(190) == 5


def test_minutes_splits_stream_by_fraction():
    """Metade a 135 (Z1), metade a 150 (Z2), 60 min -> 30 e 30."""

    zones = HrZones(floors=(130, 143, 156, 168, 181), method="garmin")

    minutes = zones.minutes([135] * 100 + [150] * 100, 3600)

    assert minutes == [30.0, 30.0, 0.0, 0.0, 0.0]


def test_minutes_ignores_below_z1_and_short_streams():

    zones = HrZones.from_max(180)   # Z1 a partir de 90

    assert sum(zones.minutes([80] * 100 + [170] * 100, 3600)) == 30.0
    assert zones.minutes([150] * 5, 3600) is None
    assert zones.minutes([150] * 100, 0) is None


def test_from_dict_rejects_garbage():

    assert HrZones.from_dict(None) is None
    assert HrZones.from_dict({"floors": [1, 2]}) is None
    assert HrZones.from_dict({"floors": [150, 140, 160, 170, 180]}) is None
    assert HrZones.from_dict({"floors": [130, 143, 156, 168, 181]}).floors == (
        130, 143, 156, 168, 181,
    )


def test_share_label_and_dominant_zone():
    """Distribuição real do treino de 25/09 (Garmin): 11,8 min Z1, 38,5 Z2,
    0,6 Z3."""

    minutes = [11.78, 38.5, 0.57, 0.0, 0.0]

    assert dominant_zone(minutes) == 2
    assert zone_share_label(minutes) == "Z2 76% · Z1 23% · Z3 1%"
    assert zone_share_label([0, 0, 0, 0, 0]) is None


def test_describe_ranges():

    zones = HrZones(floors=(130, 143, 156, 168, 181), method="garmin")

    assert zones.describe() == (
        "Z1 130-142 · Z2 143-155 · Z3 156-167 · Z4 168-180 · Z5 181+"
    )


# ---------------------------------------------------------------- resolver


@dataclass
class _Run:

    max_heartrate: float | None
    sport: str = "Run"


def _runner(age=34, hr_zones=None):

    return SimpleNamespace(age=age, hr_zones=hr_zones)


def test_resolver_prefers_watch_zones():

    watch = {"floors": [130, 143, 156, 168, 181], "method": "garmin:HR_RESERVE"}

    zones = HrZoneResolver.resolve(_runner(hr_zones=watch), [_Run(200)], 50)

    assert zones.floors == (130, 143, 156, 168, 181)


def test_resolver_hrr_with_observed_max_above_tanaka():
    """Tanaka(34)=184; observada 190 manda (é piso real do teto)."""

    zones = HrZoneResolver.resolve(_runner(), [_Run(190), _Run(178)], 60)

    assert zones.method == "hrr"
    assert zones.max_hr == 190
    assert zones.floors == HrZones.from_hrr(190, 60).floors


def test_resolver_falls_back_to_pct_max_without_resting():

    zones = HrZoneResolver.resolve(_runner(), [_Run(178)], None)

    assert zones.method == "max"
    assert zones.max_hr == 184


def test_resolver_ignores_implausible_peaks_and_non_runs():

    zones = HrZoneResolver.resolve(
        _runner(), [_Run(240), _Run(199, sport="Ride")], None
    )

    assert zones.max_hr == 184


def test_resolver_none_without_age_or_peaks():

    assert HrZoneResolver.resolve(_runner(age=None), [], None) is None
