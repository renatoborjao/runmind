from datetime import date, datetime

from app.application.planner.weekly_plan_matcher import (
    WeeklyPlanMatcher,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_activity

# Semana do plano: segunda 20/07 a domingo 26/07.
WEEK_START = date(2026, 7, 20)


def _session(day, distance, code="EASY") -> PlannedSession:

    return PlannedSession(
        day=day,
        workout_type=code,
        objective="",
        planned_distance_km=distance,
        planned_duration_minutes=None,
        target_pace_min=None,
        target_pace_max=None,
    )


def _plan(sessions) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato",
        objective="10k",
        phase="BUILD",
        weekly_volume=17.0,
        running_days=["Tuesday", "Thursday", "Saturday"],
        week_start=WEEK_START,
        sessions=sessions,
    )


def _run(day_offset, distance_km, activity_id):
    """Corrida no dia WEEK_START + offset, às 7h."""

    day = WEEK_START.replace(day=20 + day_offset)

    return make_activity(
        id=activity_id,
        start_date=datetime(day.year, day.month, day.day, 7, 0, 0),
        distance=distance_km * 1000,
    )


# Plano típico: rodagem 3.5 (ter), intervalado 4.2 (qui), longão 9.1 (sáb)
def _typical_plan() -> TrainingPlan:

    return _plan([
        _session("Tuesday", 3.5, "EASY"),
        _session("Thursday", 4.2, "VO2"),
        _session("Saturday", 9.1, "LONG_RUN"),
    ])


def test_off_day_runs_credit_the_closest_planned_session():
    """Cenário do Renato: plano Ter/Qui/Sáb, mas treinou Seg/Qua/Sáb."""

    plan = _typical_plan()

    monday = _run(0, 3.6, 1)   # ~ rodagem 3.5
    wednesday = _run(2, 4.0, 2)  # ~ intervalado 4.2
    saturday = _run(5, 9.0, 3)   # ~ longão 9.1

    activities = [saturday, wednesday, monday]  # ordem qualquer

    assert (
        WeeklyPlanMatcher.match(plan, activities, monday).planned_distance_km
        == 3.5
    )
    assert (
        WeeklyPlanMatcher.match(plan, activities, wednesday).planned_distance_km
        == 4.2
    )
    assert (
        WeeklyPlanMatcher.match(plan, activities, saturday).planned_distance_km
        == 9.1
    )


def test_surplus_run_is_extra():
    """4ª corrida (domingo) além das 3 sessões = treino extra (None)."""

    plan = _typical_plan()

    monday = _run(0, 3.6, 1)
    wednesday = _run(2, 4.0, 2)
    saturday = _run(5, 9.0, 3)
    sunday = _run(6, 5.0, 4)  # extra

    activities = [monday, wednesday, saturday, sunday]

    assert WeeklyPlanMatcher.match(plan, activities, sunday) is None


def test_single_long_run_credits_the_long_session():
    """Uma corrida só de 8.5km credita o longão de 9.1, não a rodagem."""

    plan = _typical_plan()

    run = _run(5, 8.5, 1)

    matched = WeeklyPlanMatcher.match(plan, [run], run)

    assert matched.planned_distance_km == 9.1


def test_activity_outside_plan_week_is_extra():
    """Corrida fora da semana do plano não consome sessão (None)."""

    plan = _typical_plan()

    # 5 dias antes do início da semana do plano
    outside = make_activity(
        id=9,
        start_date=datetime(2026, 7, 15, 7, 0, 0),
        distance=4000.0,
    )

    assert WeeklyPlanMatcher.match(plan, [outside], outside) is None


def test_no_sessions_means_extra():
    """Plano sem sessões (ex.: externo ainda vazio) -> tudo é extra."""

    plan = _plan([])

    run = _run(1, 5.0, 1)

    assert WeeklyPlanMatcher.match(plan, [run], run) is None


def test_run_on_a_planned_day_matches_that_day_over_distance():
    """Bug do Renato: treinou no SÁBADO (dia do longão); mesmo correndo
    uma distância curta, casa com a sessão do sábado — não com a de menor
    diferença de distância (o intervalado de 4.2)."""

    plan = _typical_plan()  # Ter 3.5, Qui 4.2, Sáb 9.1

    saturday_short = _run(5, 4.3, 1)  # sábado, mas correu só 4.3 km

    matched = WeeklyPlanMatcher.match(plan, [saturday_short], saturday_short)

    assert matched.day == "Saturday"
    assert matched.planned_distance_km == 9.1


def test_distance_fallback_is_chronological_not_by_id():
    """Fora dos dias do plano, o fallback por distância respeita a ordem
    cronológica, independente do id."""

    plan = _plan([
        _session("Tuesday", 4.0, "EASY"),
        _session("Saturday", 9.0, "LONG_RUN"),
    ])

    # dias FORA do plano (segunda e quarta): cai na distância
    long_first = _run(0, 9.0, 50)   # segunda, longo
    easy_later = _run(2, 4.0, 10)   # quarta, leve

    activities = [easy_later, long_first]

    assert (
        WeeklyPlanMatcher.match(plan, activities, long_first).planned_distance_km
        == 9.0
    )
    assert (
        WeeklyPlanMatcher.match(plan, activities, easy_later).planned_distance_km
        == 4.0
    )
