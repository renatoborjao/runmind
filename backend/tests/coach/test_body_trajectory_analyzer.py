from datetime import date, datetime, time

from app.application.coach.intelligence.body_trajectory_analyzer import (
    BodyTrajectoryAnalyzer,
)
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BALANCED,
    BODY_FRESH,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    BodyReading,
    RecoveryTrend,
)
from app.domain.entities.body_reading_snapshot import (
    TRAJ_FIRST,
    TRAJ_IMPROVED,
    TRAJ_PERSISTING,
    TRAJ_WORSENED,
    BodyReadingSnapshot,
)
from app.domain.entities.training_load import TrainingLoad

TODAY = date(2026, 7, 20)


def _reading(state) -> BodyReading:

    return BodyReading(
        load=TrainingLoad(
            acute_load=1.0, chronic_load=1.0, acwr=1.0,
            status="OPTIMAL", days_of_history=28,
        ),
        recovery=RecoveryTrend(days_covered=14),
        body_state=state,
    )


def _snap(state, day: date) -> BodyReadingSnapshot:

    return BodyReadingSnapshot(
        at=datetime.combine(day, time(20, 0)).isoformat(),
        body_state=state,
        limiter=None,
        acwr=1.0,
        acwr_status="OPTIMAL",
        hrv_recent=40.0,
        hrv_direction="stable",
        rhr_recent=55,
        rhr_direction="stable",
        sleep_avg_hours=7.0,
        short_nights=0,
        nights_counted=7,
    )


def test_first_reading_has_no_note():

    traj = BodyTrajectoryAnalyzer.of([], _reading(BODY_STRAINED), TODAY)

    assert traj.movement == TRAJ_FIRST
    assert traj.previous_state is None
    assert traj.alert_streak == 1     # atual é alerta
    assert traj.athlete_note == ""    # nada com que comparar
    assert traj.fact == ""


def test_persisting_second_reading():

    history = [_snap(BODY_STRAINED, date(2026, 7, 13))]

    traj = BodyTrajectoryAnalyzer.of(history, _reading(BODY_STRAINED), TODAY)

    assert traj.movement == TRAJ_PERSISTING
    assert traj.alert_streak == 2
    assert "2ª leitura seguida" in traj.athlete_note
    assert "PERSISTING" in traj.fact


def test_persisting_counts_streak_across_readings():

    history = [
        _snap(BODY_STRAINED, date(2026, 6, 29)),
        _snap(BODY_RECOVERY_FLAG, date(2026, 7, 6)),
        _snap(BODY_STRAINED, date(2026, 7, 13)),
    ]

    traj = BodyTrajectoryAnalyzer.of(history, _reading(BODY_STRAINED), TODAY)

    assert traj.alert_streak == 4
    assert "4ª leitura seguida" in traj.athlete_note


def test_streak_breaks_when_a_green_reading_interrupts():

    history = [
        _snap(BODY_STRAINED, date(2026, 7, 6)),
        _snap(BODY_BALANCED, date(2026, 7, 13)),   # quebra a sequência
    ]

    traj = BodyTrajectoryAnalyzer.of(history, _reading(BODY_STRAINED), TODAY)

    # entrou em alerta vindo do verde: streak reinicia em 1, é piora
    assert traj.alert_streak == 1
    assert traj.movement == TRAJ_WORSENED
    assert "piora" in traj.athlete_note


def test_improved_out_of_alert_is_announced():

    history = [_snap(BODY_STRAINED, date(2026, 7, 13))]

    traj = BodyTrajectoryAnalyzer.of(history, _reading(BODY_ABSORBING), TODAY)

    assert traj.movement == TRAJ_IMPROVED
    assert traj.alert_streak == 0
    assert "melhorou" in traj.athlete_note.lower()


def test_improvement_inside_green_stays_silent():

    history = [_snap(BODY_BALANCED, date(2026, 7, 13))]

    traj = BodyTrajectoryAnalyzer.of(history, _reading(BODY_FRESH), TODAY)

    # BALANCED -> FRESH é melhora, mas ambos no verde: não vira frase (ruído)
    assert traj.movement == TRAJ_IMPROVED
    assert traj.athlete_note == ""
    # o cérebro ainda registra o fato
    assert traj.fact != ""


def test_worsening_inside_green_stays_silent():

    history = [_snap(BODY_FRESH, date(2026, 7, 13))]

    traj = BodyTrajectoryAnalyzer.of(history, _reading(BODY_BALANCED), TODAY)

    assert traj.movement == TRAJ_WORSENED
    assert traj.athlete_note == ""


def test_today_snapshot_is_ignored_in_comparison():
    """Se um snapshot de hoje vazar pro histórico, a comparação o ignora
    (compara só com dias anteriores)."""

    history = [
        _snap(BODY_STRAINED, date(2026, 7, 13)),
        _snap(BODY_ABSORBING, TODAY),   # de hoje — não pode contar
    ]

    traj = BodyTrajectoryAnalyzer.of(history, _reading(BODY_STRAINED), TODAY)

    assert traj.previous_state == BODY_STRAINED
    assert traj.movement == TRAJ_PERSISTING
