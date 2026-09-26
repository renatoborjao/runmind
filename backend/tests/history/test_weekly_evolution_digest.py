from datetime import date, datetime, timezone

from app.application.history.weekly_evolution_digest import (
    WeeklyEvolutionDigest,
)
from app.domain.entities.body_reading_snapshot import BodyReadingSnapshot
from tests.coach.factories import make_activity

# sábado; a semana corrente começa na segunda 21/09
TODAY = date(2026, 9, 26)


def _run(day, km, minutes, hr, act_id=1):
    return make_activity(
        id=act_id,
        start_date=datetime(2026, 9, day, 9, 0, tzinfo=timezone.utc),
        distance=km * 1000, moving_time=minutes * 60, average_heartrate=hr,
    )


def _snap(day, state="RECOVERY_FLAG", sleep=6.3):
    return BodyReadingSnapshot(
        at=f"2026-09-{day:02d}T08:00:00-03:00", body_state=state,
        limiter="sono", acwr=0.76, acwr_status="DETRAINING", hrv_recent=48,
        hrv_direction="falling", rhr_recent=70, rhr_direction="falling",
        sleep_avg_hours=sleep, short_nights=6, nights_counted=14,
    )


def test_weekly_rows_with_cardiac_cost_and_body():

    acts = [
        _run(15, 8.9, 50, 156, 1),   # semana de 14/09
        _run(19, 10.7, 60, 161, 2),
        _run(22, 8.3, 45, 155, 3),   # semana corrente (21/09)
        _run(26, 13.4, 75, 159, 4),
    ]

    stats = WeeklyEvolutionDigest.build(acts, [_snap(26)], TODAY, weeks=2)

    prev, cur = stats

    assert prev.start == date(2026, 9, 14) and prev.runs == 2
    assert prev.km == 19.6 and prev.longest_km == 10.7
    assert cur.runs == 2 and cur.body is not None
    # custo cardíaco = batimentos totais / km
    expected = round((155 * 45 + 159 * 75) / (8.3 + 13.4))
    assert cur.beats_per_km == expected

    text = WeeklyEvolutionDigest.render(acts, [_snap(26)], TODAY, weeks=2)

    assert "21/09 (em andamento)" in text
    assert "recuperação em queda" in text and "sono 6.3h" in text


def test_empty_weeks_show_and_trend_compares_closed_weeks():

    acts = [
        _run(1, 5, 30, 160, 1),      # semana 31/08
        _run(8, 5, 30, 160, 2),      # semana 07/09
        _run(15, 10, 58, 150, 3),    # semana 14/09
        _run(22, 10, 57, 148, 4),    # corrente
    ]

    text = WeeklyEvolutionDigest.render(acts, [], TODAY, weeks=8)

    assert "sem corrida" in text
    assert "Tendência" in text and "mais eficiente" in text


def test_no_runs_renders_nothing():

    assert WeeklyEvolutionDigest.render([], [], TODAY) == ""
