from app.application.coach.writer.body_reading_writer import (
    BodyReadingWriter,
)
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BUILDING,
    BODY_STRAINED,
    FALLING,
    RISING,
    BodyReading,
    RecoveryTrend,
)
from app.domain.entities.body_reading_snapshot import (
    TRAJ_PERSISTING,
    BodyTrajectory,
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


def _traj(note="É a 2ª leitura seguida assim, vale levar a sério."):

    return BodyTrajectory(
        movement=TRAJ_PERSISTING,
        alert_streak=2,
        previous_state=BODY_STRAINED,
        athlete_note=note,
        fact="Trajetória do corpo: agora STRAINED...",
    )


def test_trajectory_note_enters_the_facts_for_the_ai():

    facts = BodyReadingWriter._facts(
        _reading(body_state=BODY_STRAINED), "Fernanda", _traj()
    )

    assert "Trajetória: É a 2ª leitura seguida" in facts


def test_trajectory_folds_into_verdict_block_on_fallback():

    text = BodyReadingWriter._fallback(
        _reading(body_state=BODY_STRAINED), "Fernanda", _traj()
    )

    # a frase de trajetória vem colada no bloco do veredito (⚖️)
    verdict_block = text.split("❤️")[0]

    assert "2ª leitura seguida" in verdict_block


def test_no_trajectory_keeps_message_identical():
    """Flag off => trajectory=None => mensagem idêntica à de hoje."""

    reading = _reading(body_state=BODY_STRAINED)

    assert (
        BodyReadingWriter._fallback(reading, "Fernanda", None)
        == BodyReadingWriter._fallback(reading, "Fernanda")
    )

    assert "Trajetória" not in BodyReadingWriter._facts(reading, "Fernanda")


def _reading_with_acwr(acwr, status, state):

    r = _reading(body_state=state)
    r.load.acwr = acwr
    r.load.status = status
    return r


def test_borderline_acwr_is_flagged_as_frontier_in_facts():

    # 1.31 encostado no corte de 1.30 -> a IA recebe "fronteira", não susto
    facts = BodyReadingWriter._facts(
        _reading_with_acwr(1.31, "CAUTION", BODY_STRAINED), "Fernanda"
    )

    assert "fronteira" in facts


def test_borderline_acwr_softens_fallback_verdict():

    text = BodyReadingWriter._fallback(
        _reading_with_acwr(1.31, "CAUTION", BODY_STRAINED), "Fernanda"
    )

    assert "no limite da faixa" in text


def test_non_borderline_acwr_has_no_frontier_note():

    facts = BodyReadingWriter._facts(
        _reading_with_acwr(1.74, "HIGH", BODY_STRAINED), "Fernanda"
    )

    assert "fronteira" not in facts
