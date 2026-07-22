from app.application.coach.writer.body_reading_writer import (
    BodyReadingWriter,
)
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BUILDING,
    FALLING,
    RISING,
    BodyReading,
    RecoveryTrend,
)
from app.domain.entities.training_load import TrainingLoad


def _reading(body_state=BODY_ABSORBING, limiter="sono", **rec_kwargs):

    defaults = dict(
        hrv_recent=52.0,
        hrv_direction=RISING,
        rhr_recent=60.0,
        rhr_direction=RISING,
        sleep_avg_hours=5.2,
        short_nights=6,
        nights_counted=10,
        stress_avg=30.0,
        body_battery_recent=40.0,
        vo2max=44.4,
        days_covered=12,
    )

    defaults.update(rec_kwargs)

    return BodyReading(
        load=TrainingLoad(
            acute_load=400.0,
            chronic_load=230.0,
            acwr=1.74,
            status="HIGH",
            days_of_history=28,
            weekly_loads=[137.0, 107.0, 312.0, 407.0],
        ),
        recovery=RecoveryTrend(**defaults),
        body_state=body_state,
        limiter=limiter,
    )


def test_fallback_is_structured_in_sections():

    text = BodyReadingWriter._fallback(_reading(), "Renato")

    # título + seções separadas por linha em branco (nunca parágrafo único)
    assert text.startswith("🩺 Leitura do corpo\n\n")
    assert "⚖️" in text
    assert "❤️" in text
    assert "🎯" in text
    assert "sono" in text  # limitador acionável presente


def test_fallback_without_limiter_skips_action_section():

    text = BodyReadingWriter._fallback(_reading(limiter=None), "Renato")

    assert "🎯" not in text
    assert "⚖️" in text


def test_fallback_signals_translate_directions():

    signals = BodyReadingWriter._fallback_signals(
        _reading(hrv_direction=RISING, rhr_direction=FALLING)
    )

    assert "HRV subindo, bom sinal" in signals
    assert "FC de repouso subindo, atenção" in signals
    assert "5.2h" in signals


def test_fallback_signals_none_without_recovery_data():

    reading = _reading(
        hrv_recent=None,
        rhr_recent=None,
        sleep_avg_hours=None,
        short_nights=0,
        nights_counted=0,
        stress_avg=None,
        body_battery_recent=None,
        vo2max=None,
        days_covered=0,
    )

    assert BodyReadingWriter._fallback_signals(reading) is None

    # e a mensagem segue de pé, só sem o bloco de sinais
    text = BodyReadingWriter._fallback(reading, "Renato")

    assert "❤️" not in text
    assert "⚖️" in text


def test_fallback_building_state_has_honest_text():

    text = BodyReadingWriter._fallback(
        _reading(body_state=BODY_BUILDING, limiter=None), "Renato"
    )

    assert "juntando seu histórico" in text
