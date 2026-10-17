from app.application.coach.writer.sleep_reading_writer import (
    SleepReadingWriter,
)
from app.domain.entities.body_reading import FALLING, STABLE
from app.domain.entities.sleep_reading import SleepReading


def test_no_data_returns_none():

    assert SleepReadingWriter.write(SleepReading(), "Renato") is None


def test_card_shows_average_and_debt_closing():

    reading = SleepReading(
        avg_hours=5.8,
        direction=STABLE,
        nights_counted=12,
        short_nights=9,
        last_night_hours=5.5,
        consistency="irregular",
        debt=True,
    )

    card = SleepReadingWriter.write(reading, "Renato")

    assert "Renato" in card
    assert "5h48/noite" in card
    assert "9 de 12" in card
    assert "irregular" in card
    # fecho de dívida, orientador (sem cobrar)
    assert "não é cobrança" in card.lower() or "não é cobrança" in card


def test_card_shows_garmin_score_when_present():

    reading = SleepReading(
        avg_hours=7.2, nights_counted=10, sleep_score=78, consistency="regular",
    )

    card = SleepReadingWriter.write(reading, "Ana")

    assert "78/100" in card


def test_falling_trend_closing():

    reading = SleepReading(
        avg_hours=7.1, direction=FALLING, nights_counted=8, consistency="regular",
    )

    card = SleepReadingWriter.write(reading, "Ana")

    assert "caindo" in card


# ---- veredito sono × execução (o analisador novo: HURTS / SUSTAINS) ----------


def _short_sleeper():

    return SleepReading(
        avg_hours=6.2, direction=STABLE, nights_counted=12, short_nights=8,
    )


def test_card_shows_cost_when_short_sleep_hurts_execution():

    from app.application.history.sleep_performance_analyzer import (
        SLEEP_HURTS,
        SleepPerformanceReading,
    )

    impact = SleepPerformanceReading(
        direction=SLEEP_HURTS, runs_short=5, runs_rested=5,
        short_sleep_h=6.2, rested_sleep_h=7.5, pace_delta_sec=14,
    )

    card = SleepReadingWriter.write(_short_sleeper(), "Renato", impact=impact)

    assert "~14s/km mais lento" in card
    assert "6h12" in card and "7h30" in card


def test_card_does_not_celebrate_when_short_sleep_sustains():
    """SUSTAINS é do coach (não trava a dose); o cartão não exalta o sono curto."""

    from app.application.history.sleep_performance_analyzer import (
        SLEEP_SUSTAINS,
        SleepPerformanceReading,
    )

    impact = SleepPerformanceReading(
        direction=SLEEP_SUSTAINS, runs_short=4, runs_rested=4,
        short_sleep_h=6.0, rested_sleep_h=7.0, pace_delta_sec=1,
    )

    base = SleepReadingWriter.write(_short_sleeper(), "Renato")

    assert SleepReadingWriter.write(
        _short_sleeper(), "Renato", impact=impact
    ) == base


def test_card_has_no_verdict_line_without_ground():

    from app.application.history.sleep_performance_analyzer import (
        SLEEP_INSUFFICIENT,
        SleepPerformanceReading,
    )

    base = SleepReadingWriter.write(_short_sleeper(), "Renato")

    with_insufficient = SleepReadingWriter.write(
        _short_sleeper(), "Renato",
        impact=SleepPerformanceReading(direction=SLEEP_INSUFFICIENT),
    )

    assert with_insufficient == base
