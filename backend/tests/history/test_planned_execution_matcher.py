from datetime import date, datetime

from app.application.history.planned_execution_matcher import (
    PlannedExecutionMatcher,
)
from app.domain.entities.activity import Activity
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.workout_step import WorkoutStep


def _activity(raw: dict) -> Activity:

    return Activity(
        id=1, name="Treino", sport="Run",
        start_date=datetime(2026, 7, 14, 7, 0, 0), timezone="UTC",
        distance=9000, moving_time=2700, elapsed_time=2700,
        average_speed=3.3, max_speed=3.6,
        average_heartrate=150, max_heartrate=174,
        elevation_gain=10, elevation_high=None, elevation_low=None,
        start_latitude=None, start_longitude=None,
        end_latitude=None, end_longitude=None,
        kudos=0, comments=0, suffer_score=None,
        raw=raw,
    )


def _session(steps: list[WorkoutStep]) -> PlannedSession:

    return PlannedSession(
        day="Tuesday", workout_type="Ritmo", objective="",
        planned_distance_km=9.0, planned_duration_minutes=None,
        target_pace_min=None, target_pace_max=None,
        steps=steps,
    )


def _block(kind, distance_m=0, duration_s=0, pace=None, hr=None):

    return {
        "kind": kind, "distance_m": distance_m, "duration_s": duration_s,
        "pace": pace, "avg_hr": hr, "peak_hr": hr,
    }


# --------------------------------------------------------------------
# flatten
# --------------------------------------------------------------------

def test_flatten_expands_repeat_into_numbered_blocks():

    steps = [
        WorkoutStep(kind="warmup", distance_m=2000),
        WorkoutStep(
            kind="repeat", reps=3,
            steps=[
                WorkoutStep(kind="interval", distance_m=600,
                            pace_min="5:15", pace_max="5:30"),
                WorkoutStep(kind="recovery", distance_m=400),
            ],
        ),
        WorkoutStep(kind="cooldown", distance_m=1000),
    ]

    flat = PlannedExecutionMatcher._flatten(steps)

    labels = [b["label"] for b in flat]

    assert labels == [
        "Aquecimento",
        "Tiro 1", "Recuperação 1",
        "Tiro 2", "Recuperação 2",
        "Tiro 3", "Recuperação 3",
        "Desaquecimento",
    ]


# --------------------------------------------------------------------
# match: casos limpos
# --------------------------------------------------------------------

def test_clean_match_tempo_run_with_warmup_and_cooldown():
    """Aquecimento + série de tempo + desaquecimento, tudo batendo 1:1 em
    ordem -- o caso comum de um treino guiado seguido à risca."""

    planned = _session([
        WorkoutStep(kind="warmup", distance_m=2000),
        WorkoutStep(kind="run", distance_m=6000,
                    pace_min="4:45", pace_max="4:55"),
        WorkoutStep(kind="cooldown", distance_m=1000),
    ])

    executed = [
        _block("other", 2010, 750, pace=6.2, hr=130),
        _block("effort", 6080, 1720, pace=4.72, hr=165),  # 4:43/km, dentro
        _block("other", 1000, 375, pace=6.25, hr=125),
    ]

    comparison = PlannedExecutionMatcher.match(
        planned, _activity({"_garmin_typed_blocks": executed})
    )

    assert comparison is not None
    assert not comparison.missing
    assert comparison.extra == 0
    assert len(comparison.blocks) == 3

    tempo_block = comparison.blocks[1]

    assert tempo_block.label == "Corrida contínua"
    assert tempo_block.within_target is True

    # aquecimento tem alvo de DISTÂNCIA (não pace) -> também recebe veredito
    assert comparison.blocks[0].within_target is True


def test_block_without_any_target_has_no_verdict():
    """Passo livre (sem pace nem distância/duração alvo) não recebe
    veredito -- não é 'certo' nem 'errado', é livre."""

    planned = _session([
        WorkoutStep(kind="warmup"),
    ])

    executed = [_block("other", 2010, 750, pace=6.2, hr=130)]

    comparison = PlannedExecutionMatcher.match(
        planned, _activity({"_garmin_typed_blocks": executed})
    )

    assert comparison is not None
    assert comparison.blocks[0].within_target is None


def test_interval_block_outside_target_flags_false():

    planned = _session([
        WorkoutStep(kind="interval", distance_m=600,
                    pace_min="5:15", pace_max="5:30"),
    ])

    executed = [_block("effort", 600, 216, pace=6.0, hr=160)]  # 6:00, fora

    comparison = PlannedExecutionMatcher.match(
        planned, _activity({"_garmin_typed_blocks": executed})
    )

    assert comparison is not None
    assert comparison.blocks[0].within_target is False


# --------------------------------------------------------------------
# match: casos ambíguos/robustez
# --------------------------------------------------------------------

def test_missing_leading_warmup_still_matches_the_rest():
    """Relógio perdeu o aquecimento (reiniciou) -- o resto casa normal."""

    planned = _session([
        WorkoutStep(kind="warmup", distance_m=2000),
        WorkoutStep(kind="interval", distance_m=600,
                    pace_min="5:15", pace_max="5:30"),
    ])

    executed = [_block("effort", 610, 220, pace=5.2, hr=165)]

    comparison = PlannedExecutionMatcher.match(
        planned, _activity({"_garmin_typed_blocks": executed})
    )

    assert comparison is not None
    assert comparison.missing == ["Aquecimento"]
    assert len(comparison.blocks) == 1
    assert comparison.blocks[0].label == "Tiro 1"


def test_phantom_lap_in_the_middle_is_skipped():
    """Volta-fantasma inesperada entre dois tiros não atrapalha o resto,
    contanto que esteja dentro da janela de busca."""

    planned = _session([
        WorkoutStep(kind="interval", distance_m=600,
                    pace_min="5:15", pace_max="5:30"),
        WorkoutStep(kind="recovery", distance_m=400),
        WorkoutStep(kind="interval", distance_m=600,
                    pace_min="5:15", pace_max="5:30"),
    ])

    executed = [
        _block("effort", 600, 216, pace=5.2, hr=165),
        _block("other", 8, 3, pace=None, hr=None),   # lap-fantasma
        _block("recovery", 400, 168, pace=7.0, hr=140),
        _block("effort", 600, 216, pace=5.25, hr=168),
    ]

    comparison = PlannedExecutionMatcher.match(
        planned, _activity({"_garmin_typed_blocks": executed})
    )

    assert comparison is not None
    assert not comparison.missing
    assert len(comparison.blocks) == 3
    assert comparison.extra == 1


def test_athlete_stopped_before_finishing_flags_missing_not_wrong_match():
    """5 tiros planejados, atleta parou no 4º -- reporta HONESTAMENTE que
    faltou o 5º, não casa errado."""

    planned = _session([
        WorkoutStep(
            kind="repeat", reps=5,
            steps=[
                WorkoutStep(kind="interval", distance_m=600,
                            pace_min="5:15", pace_max="5:30"),
                WorkoutStep(kind="recovery", distance_m=400),
            ],
        ),
    ])

    executed = []

    for _ in range(4):

        executed.append(_block("effort", 600, 216, pace=5.2, hr=165))
        executed.append(_block("recovery", 400, 168, pace=7.0, hr=140))

    comparison = PlannedExecutionMatcher.match(
        planned, _activity({"_garmin_typed_blocks": executed})
    )

    assert comparison is not None
    assert comparison.missing == ["Tiro 5", "Recuperação 5"]
    assert len(comparison.blocks) == 8


def test_too_ambiguous_gives_up_and_returns_none():
    """Mais de 30% dos blocos esperados sem par confiável -- desiste em vez
    de arriscar um pareamento errado."""

    planned = _session([
        WorkoutStep(
            kind="repeat", reps=5,
            steps=[
                WorkoutStep(kind="interval", distance_m=600,
                            pace_min="5:15", pace_max="5:30"),
                WorkoutStep(kind="recovery", distance_m=400),
            ],
        ),
    ])

    # só 1 dos 10 blocos esperados tem par
    executed = [_block("effort", 600, 216, pace=5.2, hr=165)]

    comparison = PlannedExecutionMatcher.match(
        planned, _activity({"_garmin_typed_blocks": executed})
    )

    assert comparison is None


def test_no_planned_steps_returns_none():
    """Treinador externo / plano sem estrutura: sem `steps`, sem
    comparação -- cai no caminho de hoje (texto livre pra IA)."""

    planned = _session([])

    comparison = PlannedExecutionMatcher.match(
        planned,
        _activity({"_garmin_typed_blocks": [_block("effort", 600, 216)]}),
    )

    assert comparison is None


def test_no_garmin_typed_blocks_returns_none():
    """Atleta só com Strava (sem Garmin): raw não tem _garmin_typed_blocks
    -- sem comparação exata, comportamento de hoje intacto."""

    planned = _session([
        WorkoutStep(kind="interval", distance_m=600,
                    pace_min="5:15", pace_max="5:30"),
    ])

    comparison = PlannedExecutionMatcher.match(planned, _activity({}))

    assert comparison is None
