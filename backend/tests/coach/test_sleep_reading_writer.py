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
