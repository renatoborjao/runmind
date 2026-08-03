from datetime import date

from app.application.history.streak_calculator import StreakCalculator
from app.domain.entities.adherence_report import WeekAdherence


def _week(planned, done, wk=1) -> WeekAdherence:

    return WeekAdherence(week_start=date(2026, 7, wk), planned=planned, done=done)


def test_counts_trailing_hit_weeks():

    weeks = [_week(3, 1), _week(3, 3), _week(3, 3), _week(3, 3)]

    assert StreakCalculator.consecutive_weeks(weeks) == 3


def test_break_resets_streak_to_recent_only():

    weeks = [_week(3, 3), _week(3, 1), _week(3, 3)]

    assert StreakCalculator.consecutive_weeks(weeks) == 1


def test_week_without_plan_is_neutral():
    """Semana sem plano (planned=0) não conta nem quebra a sequência."""

    weeks = [_week(3, 3), _week(0, 0), _week(3, 3)]

    assert StreakCalculator.consecutive_weeks(weeks) == 2


def test_no_streak_when_last_week_missed():

    weeks = [_week(3, 3), _week(3, 3), _week(3, 1)]

    assert StreakCalculator.consecutive_weeks(weeks) == 0


def test_eighty_percent_counts_as_hit():
    """4 de 5 (80%) conta; 3 de 5 (60%) não."""

    assert StreakCalculator.consecutive_weeks([_week(5, 4)]) == 1
    assert StreakCalculator.consecutive_weeks([_week(5, 3)]) == 0
