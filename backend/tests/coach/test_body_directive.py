from app.application.coach.planning.body_directive import body_plan_directive
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BALANCED,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    BodyReading,
    RecoveryTrend,
)
from app.domain.entities.body_reading_snapshot import (
    TRAJ_PERSISTING,
    TRAJ_STEADY,
    BodyTrajectory,
)
from app.domain.entities.training_load import TrainingLoad


def _reading(state, limiter="sono") -> BodyReading:

    return BodyReading(
        load=TrainingLoad(
            acute_load=500.0, chronic_load=380.0, acwr=1.32,
            status="CAUTION", days_of_history=28,
        ),
        recovery=RecoveryTrend(days_covered=14),
        body_state=state,
        limiter=limiter,
    )


def _traj(movement=TRAJ_STEADY, streak=1) -> BodyTrajectory:

    return BodyTrajectory(
        movement=movement, alert_streak=streak, previous_state=None,
    )


def test_healthy_states_produce_no_directive():

    assert body_plan_directive(_reading(BODY_ABSORBING)) == ""
    assert body_plan_directive(_reading(BODY_BALANCED)) == ""


def test_strained_asks_the_coach_to_ease_and_not_the_athlete():

    directive = body_plan_directive(_reading(BODY_STRAINED))

    assert "COACH" in directive
    assert "NÃO pergunte ao atleta" in directive
    assert "RECUPERAÇÃO" in directive
    # limitador acionável presente
    assert "sono" in directive


def test_recovery_flag_weighs_against_capacity_not_a_blanket_brake():
    """RECOVERY_FLAG não é freio automático: manda PESAR contra a capacidade
    (limitador baseline que ele sustenta + carga tranquila -> não trava a
    progressão). Era o buraco do Mauricio (limiar de 15min com folga de tempo)."""

    directive = body_plan_directive(_reading(BODY_RECOVERY_FLAG))

    assert directive != ""
    # não manda cortar volume à toa (carga está ok)
    assert "à toa" in directive.lower()
    # convida a síntese em vez de um "evite subir" cego
    assert "capacidade" in directive.lower()
    assert "baseline" in directive.lower()
    assert "NÃO trave a progressão" in directive


def test_recovery_flag_persistence_points_to_learnings():
    """RECOVERY_FLAG que se repete: em vez de 'dá mais peso', manda CONFIRMAR nos
    aprendizados se é baseline (que ele sustenta) ou piora real."""

    directive = body_plan_directive(
        _reading(BODY_RECOVERY_FLAG),
        _traj(movement=TRAJ_PERSISTING, streak=3),
    )

    assert "3 leituras" in directive
    assert "APRENDIZADOS" in directive
    assert "BASELINE" in directive


def test_persistence_adds_weight():

    directive = body_plan_directive(
        _reading(BODY_STRAINED),
        _traj(movement=TRAJ_PERSISTING, streak=3),
    )

    assert "3 leituras seguidas" in directive


def test_no_persistence_note_when_not_persisting():

    directive = body_plan_directive(
        _reading(BODY_STRAINED), _traj(movement=TRAJ_STEADY, streak=0)
    )

    assert "leituras seguidas" not in directive
