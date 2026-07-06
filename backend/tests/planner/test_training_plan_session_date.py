from datetime import date

from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan

WEEK_START = date(2026, 7, 20)  # segunda-feira


def _session(day: str) -> PlannedSession:

    return PlannedSession(
        day=day,
        workout_type="Easy Run",
        objective="Base",
        planned_distance_km=8.0,
        planned_duration_minutes=None,
        target_pace_min=None,
        target_pace_max=None,
    )


def _plan(sessions: list[PlannedSession]) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato",
        objective="10k",
        phase="BUILD",
        weekly_volume=30.0,
        running_days=["Monday", "Wednesday", "Sunday"],
        week_start=WEEK_START,
        sessions=sessions,
    )


def test_session_date_monday_matches_week_start():

    plan = _plan([_session("Monday")])

    assert plan.session_date(plan.sessions[0]) == date(2026, 7, 20)


def test_session_date_wednesday_offset():

    plan = _plan([_session("Wednesday")])

    assert plan.session_date(plan.sessions[0]) == date(2026, 7, 22)


def test_session_date_sunday_end_of_week():

    plan = _plan([_session("Sunday")])

    assert plan.session_date(plan.sessions[0]) == date(2026, 7, 26)


def test_session_date_is_case_insensitive():

    plan = _plan([_session("wednesday")])

    assert plan.session_date(plan.sessions[0]) == date(2026, 7, 22)


def test_next_session_after_picks_first_upcoming():

    plan = _plan([
        _session("Sunday"),
        _session("Monday"),
        _session("Wednesday"),
    ])

    # terça (21/07): próxima sessão é quarta, não domingo
    next_session = plan.next_session_after(date(2026, 7, 21))

    assert next_session.day == "Wednesday"


def test_next_session_after_is_strictly_after_reference():

    plan = _plan([_session("Monday"), _session("Sunday")])

    # na própria segunda, a próxima é domingo (não a de hoje)
    next_session = plan.next_session_after(date(2026, 7, 20))

    assert next_session.day == "Sunday"


def test_next_session_after_returns_none_past_last_session():

    plan = _plan([_session("Monday"), _session("Wednesday")])

    assert plan.next_session_after(date(2026, 7, 22)) is None


def test_next_session_after_skips_already_done_days():

    plan = _plan([
        _session("Monday"),
        _session("Wednesday"),
        _session("Sunday"),
    ])

    # fez o longão de domingo adiantado (na segunda): quarta é a próxima,
    # e domingo não deve reaparecer como "próximo"
    next_session = plan.next_session_after(
        date(2026, 7, 20),
        done_days={"Sunday"},
    )

    assert next_session.day == "Wednesday"


def test_next_session_after_none_when_only_remaining_is_done():

    plan = _plan([_session("Monday"), _session("Sunday")])

    # domingo já cumprido e nada mais à frente -> sem próximo
    assert plan.next_session_after(
        date(2026, 7, 20),
        done_days={"Sunday"},
    ) is None
