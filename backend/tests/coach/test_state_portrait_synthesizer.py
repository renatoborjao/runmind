from app.application.coach.intelligence.state_portrait_synthesizer import (
    StatePortraitSynthesizer,
)
from app.domain.entities.aerobic_efficiency import AerobicEfficiency
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BUILDING,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    BodyReading,
    RecoveryTrend,
)
from app.domain.entities.fitness_evolution import (
    EVO_IMPROVING,
    EVO_INSUFFICIENT,
    EVO_STABLE,
    FitnessEvolution,
)
from app.domain.entities.training_load import LOAD_OPTIMAL, TrainingLoad


def _reading(body_state, has_recovery=True):

    rec = RecoveryTrend(days_covered=5 if has_recovery else 0)

    load = TrainingLoad(
        acute_load=100, chronic_load=95, acwr=1.05,
        status=LOAD_OPTIMAL, days_of_history=40,
        weekly_loads=[90, 95, 100, 105],
    )

    return BodyReading(load=load, recovery=rec, body_state=body_state)


def _evo(direction=EVO_STABLE, days=5):

    ef = (
        AerobicEfficiency(direction="STABLE", runs_counted=8, weeks_covered=8)
        if direction != EVO_INSUFFICIENT
        else None
    )

    return FitnessEvolution(
        direction=direction, ef=ef, days_since_last_run=days,
    )


# -- o coração: a leitura CRUZADA --------------------------------------

def test_green_body_plus_improving_is_the_progress_window():
    """Corpo absorvendo + forma subindo = a janela ideal pra progredir."""

    state, conduct = StatePortraitSynthesizer.synthesize(
        _reading(BODY_ABSORBING), _evo(EVO_IMPROVING),
    )

    assert "janela" in state.lower()
    assert "progredir" in state.lower()
    assert "progride a dose" in conduct.lower()


def test_strained_body_plus_improving_protects_the_gain():
    """Evoluiu MAS corpo pede freio: aliviar protege o ganho (não é recuo)."""

    state, conduct = StatePortraitSynthesizer.synthesize(
        _reading(BODY_STRAINED), _evo(EVO_IMPROVING),
    )

    assert "respiro" in state.lower() or "protege" in state.lower()
    assert "alivia" in conduct.lower() or "recuperar" in conduct.lower()


def test_yellow_body_plus_improving_warns_not_to_trade_gain_for_fatigue():

    state, _ = StatePortraitSynthesizer.synthesize(
        _reading(BODY_RECOVERY_FLAG), _evo(EVO_IMPROVING),
    )

    assert "fadiga" in state.lower()


# -- degradação graciosa (um eixo sem leitura) -------------------------

def test_body_only_when_fitness_has_no_lastro():
    """Sem lastro de forma: a síntese fala só do corpo, sem inventar forma."""

    state, conduct = StatePortraitSynthesizer.synthesize(
        _reading(BODY_ABSORBING), _evo(EVO_INSUFFICIENT, days=None),
    )

    assert "corpo" in state.lower()
    assert "forma" not in state.lower()


def test_fitness_only_when_no_recovery_data():
    """Atleta só-Strava (sem recuperação): a síntese fala só da forma."""

    state, _ = StatePortraitSynthesizer.synthesize(
        _reading(BODY_BUILDING, has_recovery=False), _evo(EVO_IMPROVING),
    )

    assert "forma" in state.lower()


def test_stale_fitness_counts_as_no_fitness_reading():
    """Dado velho (parou de correr) não vota como forma — cai no corpo-só."""

    state, _ = StatePortraitSynthesizer.synthesize(
        _reading(BODY_ABSORBING), _evo(EVO_IMPROVING, days=30),
    )

    assert "corpo" in state.lower()
    assert "forma" not in state.lower()


def test_nothing_to_read_gives_building_message():

    state, conduct = StatePortraitSynthesizer.synthesize(
        _reading(BODY_BUILDING, has_recovery=False),
        _evo(EVO_INSUFFICIENT, days=None),
    )

    assert "juntando" in state.lower() or "histórico" in state.lower()
