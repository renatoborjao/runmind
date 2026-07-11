from datetime import date

from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


def _isolated_repo(tmp_path):

    repo = WeeklyPlanRepository()

    repo.storage = tmp_path

    return repo


def _plan() -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato",
        objective="10k",
        phase="BUILD",
        weekly_volume=30.0,
        running_days=["Monday", "Wednesday", "Sunday"],
        week_start=date(2026, 7, 20),
        sessions=[
            PlannedSession(
                day="Monday",
                workout_type="Easy Run",
                objective="Base",
                planned_distance_km=8.0,
                planned_duration_minutes=None,
                target_pace_min="5:12",
                target_pace_max="5:48",
                notes="Rodagem leve.",
            ),
        ],
    )


def test_structured_steps_survive_the_disk_as_workout_steps(tmp_path):

    # regressão: steps salvos por asdict voltavam como dict e o push guiado
    # do Garmin quebrava (dict não tem .is_repeat) — tiro sumia do relógio
    from app.application.garmin.garmin_workout_builder import (
        GarminWorkoutBuilder,
    )
    from app.domain.entities.workout_step import WorkoutStep

    repo = _isolated_repo(tmp_path)

    plan = _plan()
    plan.sessions[0].steps = [
        WorkoutStep(kind="warmup", distance_m=2000, pace_min="6:30"),
        WorkoutStep(
            kind="repeat",
            reps=6,
            steps=[
                WorkoutStep(kind="interval", distance_m=800, pace_min="4:45"),
                WorkoutStep(kind="recovery", distance_m=400),
            ],
        ),
    ]

    repo.save("renato", plan)

    loaded = repo.load("renato").sessions[0]

    assert all(isinstance(step, WorkoutStep) for step in loaded.steps)
    assert loaded.steps[1].is_repeat
    assert loaded.steps[1].steps[0].distance_m == 800

    # e o treino guiado monta a partir do plano recarregado (não quebra)
    GarminWorkoutBuilder.build(loaded, name="x")


def test_load_returns_none_when_no_file(tmp_path):

    repo = _isolated_repo(tmp_path)

    assert repo.load("renato") is None


def test_save_and_load_round_trip(tmp_path):

    repo = _isolated_repo(tmp_path)

    plan = _plan()

    repo.save("renato", plan)

    loaded = repo.load("renato")

    assert loaded is not None
    assert loaded.athlete_name == "Renato"
    assert loaded.week_start == date(2026, 7, 20)
    assert loaded.running_days == ["Monday", "Wednesday", "Sunday"]
    assert len(loaded.sessions) == 1
    assert loaded.sessions[0].workout_type == "Easy Run"
    assert loaded.sessions[0].target_pace_min == "5:12"


def test_save_overwrites_previous_plan(tmp_path):

    repo = _isolated_repo(tmp_path)

    repo.save("renato", _plan())

    updated = _plan()
    updated.weekly_volume = 40.0

    repo.save("renato", updated)

    loaded = repo.load("renato")

    assert loaded.weekly_volume == 40.0


def test_source_round_trip_and_legacy_default(tmp_path):

    import json as _json

    from app.domain.entities.training_plan import TrainingPlan
    from datetime import date as _date

    repo = WeeklyPlanRepository()
    repo.storage = tmp_path

    external = TrainingPlan(
        athlete_name="Fulano",
        objective="10k",
        phase="EXTERNO",
        weekly_volume=20.0,
        running_days=["Tuesday"],
        week_start=_date(2026, 6, 29),
        sessions=[],
        source="externo",
    )

    repo.save("fulano", external)

    assert repo.load("fulano").source == "externo"

    # JSON antigo sem o campo source -> "runmind"
    data = _json.loads((tmp_path / "fulano.json").read_text("utf-8"))
    del data["source"]
    (tmp_path / "fulano.json").write_text(
        _json.dumps(data), encoding="utf-8",
    )

    assert repo.load("fulano").source == "runmind"


def _plan_for_week(week_start, volume=20.0):

    return TrainingPlan(
        athlete_name="Renato",
        objective="10k",
        phase="BUILD",
        weekly_volume=volume,
        running_days=["Tuesday"],
        week_start=week_start,
        sessions=[],
    )


def test_save_appends_snapshot_to_history(tmp_path):

    repo = WeeklyPlanRepository()
    repo.storage = tmp_path

    repo.save("renato", _plan_for_week(date(2026, 6, 22)))
    repo.save("renato", _plan_for_week(date(2026, 6, 29)))

    history = repo.history("renato")

    assert [p.week_start for p in history] == [
        date(2026, 6, 22),
        date(2026, 6, 29),
    ]


def test_same_week_snapshot_is_replaced_not_duplicated(tmp_path):

    repo = WeeklyPlanRepository()
    repo.storage = tmp_path

    repo.save("renato", _plan_for_week(date(2026, 6, 29), volume=20.0))
    # ajuste na mesma semana regrava o snapshot
    repo.save("renato", _plan_for_week(date(2026, 6, 29), volume=16.0))

    history = repo.history("renato")

    assert len(history) == 1
    assert history[0].weekly_volume == 16.0


def test_history_empty_without_file(tmp_path):

    repo = WeeklyPlanRepository()
    repo.storage = tmp_path

    assert repo.history("renato") == []
