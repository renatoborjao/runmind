import json

from app.application.history.hr_zone_calculator import HrZoneCalculator
from app.domain.value_objects.hr_zones import HrZones
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from tests.coach.factories import make_activity


def test_histogram_is_minutes_per_bpm_independent_of_ruler():

    stream = [150] * 60 + [160] * 30 + [0] * 10  # zeros descartados

    hist = HrZoneCalculator.histogram(stream, 90 * 60)

    assert hist == {"150": 60.0, "160": 30.0}


def test_histogram_needs_a_real_stream():

    assert HrZoneCalculator.histogram([150] * 10, 600) is None
    assert HrZoneCalculator.histogram([150] * 60, 0) is None


def test_same_histogram_reads_differently_per_ruler():
    """O MESMO treino (150 bpm) é Z4 na fórmula de idade do renato2 e Z2 no
    relógio — por isso a carga relê com UMA régua pra janela inteira."""

    hist = {"150": 60.0}

    tanaka = HrZones.from_max(184)  # Z4 começa em 147
    watch = HrZones(floors=(128, 140, 152, 164, 176), method="garmin")

    assert tanaka.minutes_from_histogram(hist) == [0.0, 0.0, 0.0, 60.0, 0.0]
    assert watch.minutes_from_histogram(hist) == [0.0, 60.0, 0.0, 0.0, 0.0]


def test_archive_keeps_histogram_when_reupserted_without_stream(tmp_path):
    """Regravar a mesma corrida vinda da lista do Strava (sem stream) não pode
    apagar o histograma/zonas que a ingestão rica calculou."""

    repo = ActivityArchiveRepository()
    repo.storage = tmp_path

    rich = make_activity(id=7, hr_zone_minutes=[1, 2, 3, 4, 0])
    rich.hr_histogram = {"150": 50.0}

    repo.upsert_many("r", [rich])

    poor = make_activity(id=7)  # mesma atividade, sem stream

    repo.upsert_many("r", [poor])

    record = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))[0]

    assert record["hr_histogram"] == {"150": 50.0}
    assert record["hr_zone_minutes"] == [1, 2, 3, 4, 0]

    assert repo.load_activities("r")[0].hr_histogram == {"150": 50.0}
