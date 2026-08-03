from datetime import date
from unittest.mock import MagicMock, patch

from app.application.coach.context.day_context_reader import DayContextReader
from app.domain.entities.daily_health import DailyHealth

MOD = "app.application.coach.context.day_context_reader"


def _patch(health_list, body_state=None, weekly_loads=None, due=False):
    """Mocka o repo de saúde e (opcionalmente) a leitura de corpo acumulada."""

    health_repo = MagicMock()
    health_repo.return_value.load.return_value = health_list

    return patch(
        "app.infrastructure.persistence.garmin_health_repository."
        "GarminHealthRepository",
        health_repo,
    )


def test_short_sleep_is_flagged():

    health = DailyHealth(date="2026-08-04", sleep_hours=5.2, readiness_level="LOW")

    with _patch([health]):
        # sem leitura de corpo (deixa a parte acumulada falhar silenciosa)
        with patch(
            "app.application.coach.intelligence.body_reading_service."
            "BodyReadingService.read",
            side_effect=RuntimeError("sem corpo"),
        ):
            out = DayContextReader.facts("renato2", date(2026, 8, 4))

    assert "CONTEXTO DO DIA" in out
    assert "5.2h (CURTO)" in out
    assert "prontidão do dia low" in out


def test_normal_sleep_not_flagged_curto():

    health = DailyHealth(date="2026-08-04", sleep_hours=7.8)

    with _patch([health]):
        with patch(
            "app.application.coach.intelligence.body_reading_service."
            "BodyReadingService.read",
            side_effect=RuntimeError("x"),
        ):
            out = DayContextReader.facts("renato2", date(2026, 8, 4))

    assert "7.8h" in out
    assert "CURTO" not in out


def test_no_health_for_date_and_no_body_gives_empty():

    with _patch([DailyHealth(date="2026-08-01", sleep_hours=7.0)]):
        with patch(
            "app.application.coach.intelligence.body_reading_service."
            "BodyReadingService.read",
            side_effect=RuntimeError("x"),
        ):
            out = DayContextReader.facts("renato2", date(2026, 8, 4))

    assert out == ""


def test_high_stress_flagged():

    health = DailyHealth(date="2026-08-04", sleep_hours=7.0, stress_avg=62)

    with _patch([health]):
        with patch(
            "app.application.coach.intelligence.body_reading_service."
            "BodyReadingService.read",
            side_effect=RuntimeError("x"),
        ):
            out = DayContextReader.facts("renato2", date(2026, 8, 4))

    assert "stress do dia alto (62)" in out
