from app.application.coach.writer.state_portrait_writer import (
    StatePortraitWriter,
)
from app.domain.entities.aerobic_efficiency import (
    EFF_IMPROVING,
    AerobicEfficiency,
)
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BUILDING,
    BodyReading,
    RecoveryTrend,
)
from app.domain.entities.fitness_evolution import (
    EVO_IMPROVING,
    EVO_INSUFFICIENT,
    FitnessEvolution,
)
from app.domain.entities.training_load import LOAD_OPTIMAL, TrainingLoad


def _reading(body_state=BODY_ABSORBING, has_recovery=True, limiter=None):

    rec = (
        RecoveryTrend(
            days_covered=5, hrv_recent=57.0, rhr_recent=48,
            sleep_avg_hours=6.4, short_nights=2, nights_counted=7,
        )
        if has_recovery
        else RecoveryTrend(days_covered=0)
    )

    load = TrainingLoad(
        acute_load=100, chronic_load=95, acwr=1.05,
        status=LOAD_OPTIMAL, days_of_history=40,
        weekly_loads=[90, 95, 100, 105],
    )

    return BodyReading(
        load=load, recovery=rec, body_state=body_state, limiter=limiter,
    )


def _evo(direction=EVO_IMPROVING, days=5, tangible=True):

    ef = (
        AerobicEfficiency(
            direction=EFF_IMPROVING, runs_counted=8, weeks_covered=8,
            ref_hr=154, pace_gain_sec=17,
        )
        if direction != EVO_INSUFFICIENT and tangible
        else (
            AerobicEfficiency(direction=EFF_IMPROVING, runs_counted=8)
            if direction != EVO_INSUFFICIENT
            else None
        )
    )

    return FitnessEvolution(
        direction=direction, ef=ef, days_since_last_run=days,
    )


def test_full_portrait_has_all_sections():

    msg = StatePortraitWriter.write(_reading(), _evo(), "Renato")

    assert "📷 Como você está, Renato" in msg
    assert "💪 Corpo:" in msg
    assert "📈 Forma:" in msg
    assert "🎯" in msg
    # painel factual de recuperação embutido na seção do corpo
    assert "Sua recuperação" in msg
    # tradução sentível do EF
    assert "17 s/km" in msg


def test_none_when_no_axis_has_data():
    """Atleta novíssimo: sem corpo E sem forma -> nada a dizer."""

    reading = _reading(BODY_BUILDING, has_recovery=False)

    evo = _evo(EVO_INSUFFICIENT, days=None)

    assert StatePortraitWriter.write(reading, evo, "Renato") is None


def test_fitness_only_portrait_skips_body_section():
    """Só-Strava (sem recuperação) ainda recebe o retrato da forma."""

    reading = _reading(BODY_BUILDING, has_recovery=False)

    msg = StatePortraitWriter.write(reading, _evo(EVO_IMPROVING), "Renato")

    assert msg is not None
    assert "💪 Corpo:" not in msg
    assert "📈 Forma:" in msg


def test_stale_fitness_section_is_honest_and_drops_tangible():
    """Dado velho: a seção de forma diz 'sem leitura fresca' e não mostra um
    número tangível antigo."""

    msg = StatePortraitWriter.write(
        _reading(), _evo(EVO_IMPROVING, days=30), "Renato",
    )

    assert "sem leitura fresca" in msg
    assert "30 dias" in msg
    assert "17 s/km" not in msg   # não vaza número velho


def test_limiter_shows_in_body_line():

    msg = StatePortraitWriter.write(
        _reading(limiter="sono"), _evo(), "Renato",
    )

    assert "atenção ao sono" in msg
