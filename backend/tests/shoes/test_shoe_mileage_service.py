from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.application.shoes.shoe_mileage_service import ShoeMileageService
from app.domain.entities.shoe import Shoe, ShoeBook, ShoeRule
from app.infrastructure.persistence.shoe_repository import ShoeRepository

MOD = "app.application.shoes.shoe_mileage_service"

PROFILE = "renato"


def _real_repo(tmp_path) -> ShoeRepository:

    repo = ShoeRepository()
    repo.storage = tmp_path
    return repo


def _enriched(dist_m=10000.0, act_id=1, day="2026-08-20", gear_id=None,
              training_type="RODAGEM"):

    activity = SimpleNamespace(
        id=act_id,
        distance=dist_m,
        start_date=datetime.fromisoformat(f"{day}T07:00:00"),
        raw={"gear_id": gear_id} if gear_id else {},
    )

    return SimpleNamespace(activity=activity, training_type=training_type)


def _run(tmp_path, book, enriched, planned=None):

    repo = _real_repo(tmp_path)
    repo.save(PROFILE, book)

    with patch(f"{MOD}.ShoeRepository", return_value=repo):

        outcome = ShoeMileageService.attribute(
            PROFILE, "Renato", enriched, planned,
        )

    return outcome, repo.load(PROFILE)


def test_accumulates_on_default_shoe(tmp_path):

    book = ShoeBook(shoes=[Shoe(id="boston", name="Boston", is_default=True)])

    outcome, saved = _run(tmp_path, book, _enriched(dist_m=10000.0))

    assert outcome is not None
    assert outcome.shoe.id == "boston"
    assert outcome.km == 10.0
    assert saved.get("boston").accumulated_km == 10.0


def test_gear_beats_default(tmp_path):

    book = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", is_default=True),
        Shoe(id="vapor", name="Vaporfly", gear_id="g1"),
    ])

    outcome, saved = _run(tmp_path, book, _enriched(gear_id="g1"))

    assert outcome.shoe.id == "vapor"
    assert saved.get("vapor").accumulated_km == 10.0
    assert saved.get("boston").accumulated_km == 0.0


def test_rotation_rule_by_workout_type(tmp_path):

    book = ShoeBook(
        shoes=[
            Shoe(id="boston", name="Boston", is_default=True),
            Shoe(id="vapor", name="Vaporfly"),
        ],
        rules=[ShoeRule(match="tiro", shoe_id="vapor")],
    )

    planned = SimpleNamespace(workout_type="Tiros")

    outcome, saved = _run(tmp_path, book, _enriched(training_type="INTERVAL"),
                          planned)

    assert outcome.shoe.id == "vapor"


def test_idempotent_same_activity_id(tmp_path):
    """Reentrega do MESMO id (id já contado) não soma de novo — guarda por id,
    independente do fingerprint cross-fonte."""

    book = ShoeBook(
        shoes=[Shoe(id="boston", name="Boston", is_default=True,
                    counted_ids=[1])],
    )

    outcome, saved = _run(tmp_path, book, _enriched(act_id=1))

    assert outcome is None
    assert saved.get("boston").accumulated_km == 0.0


def test_cross_source_dedup_same_run_two_ids(tmp_path):
    """Mesma corrida por Strava (id 1) e Garmin (id 2), mesmo dia/km: conta 1x."""

    book = ShoeBook(shoes=[Shoe(id="boston", name="Boston", is_default=True)])

    repo = _real_repo(tmp_path)
    repo.save(PROFILE, book)

    with patch(f"{MOD}.ShoeRepository", return_value=repo):

        first = ShoeMileageService.attribute(
            PROFILE, "Renato", _enriched(act_id=1, day="2026-08-20"), None,
        )
        second = ShoeMileageService.attribute(
            PROFILE, "Renato", _enriched(act_id=2, day="2026-08-20"), None,
        )

    assert first is not None and second is None
    assert repo.load(PROFILE).get("boston").accumulated_km == 10.0


def test_no_shoes_is_silent(tmp_path):

    outcome, _ = _run(tmp_path, ShoeBook(), _enriched())

    assert outcome is None


def test_wear_alert_fires_once_when_threshold_crossed(tmp_path):

    book = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", nickname="Boston", is_default=True,
             initial_km=695.0, alert_threshold_km=700.0),
    ])

    outcome, saved = _run(tmp_path, book, _enriched(dist_m=10000.0))

    assert outcome.wear_alert is not None
    assert "700" in outcome.wear_alert or "705" in outcome.wear_alert
    assert saved.get("boston").wear_alerted is True


def test_wear_alert_does_not_refire(tmp_path):

    book = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", is_default=True,
             initial_km=800.0, alert_threshold_km=700.0, wear_alerted=True),
    ])

    outcome, _ = _run(tmp_path, book, _enriched())

    assert outcome.wear_alert is None
