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
        average_speed=km * 1000 / (minutes * 60), elevation_gain=0.0,
    )


def _snap(day, state="RECOVERY_FLAG", sleep=6.3):
    return BodyReadingSnapshot(
        at=f"2026-09-{day:02d}T08:00:00-03:00", body_state=state,
        limiter="sono", acwr=0.76, acwr_status="DETRAINING", hrv_recent=48,
        hrv_direction="falling", rhr_recent=70, rhr_direction="falling",
        sleep_avg_hours=sleep, short_nights=6, nights_counted=14,
    )


def test_weekly_rows_with_body_and_no_raw_cardiac_cost():
    """A tabela não usa mais 'batimentos por km' bruto (contradizia a leitura
    'Forma'); traz volume, FC e a economia na MESMA medida da Forma."""

    acts = [
        _run(15, 8.9, 50, 156, 1),   # semana de 14/09
        _run(19, 10.7, 60, 161, 2),
        _run(22, 8.3, 45, 150, 3),   # semana corrente (21/09)
        _run(26, 13.4, 75, 152, 4),
    ]

    stats, _ = WeeklyEvolutionDigest.build(acts, [_snap(26)], TODAY, weeks=2)

    prev, cur = stats

    assert prev.start == date(2026, 9, 14) and prev.runs == 2
    assert prev.km == 19.6 and prev.longest_km == 10.7
    assert cur.runs == 2 and cur.body is not None

    text = WeeklyEvolutionDigest.render(acts, [_snap(26)], TODAY, weeks=2)

    assert "21/09 (em andamento)" in text
    assert "recuperação em queda" in text and "sono 6.3h" in text
    assert "bpm/km" not in text


def test_economy_is_the_same_measure_as_forma_and_improves_with_pace_at_same_hr():
    """Mesma FC, pace mais rápido na semana nova → economia menor (melhor).
    Com FC de repouso/máx, só corridas aeróbicas comparáveis entram."""

    acts = [
        _run(15, 8.0, 52, 145, 1),   # 6:30/km a 145
        _run(17, 8.0, 52, 145, 2),
        _run(22, 8.0, 48, 145, 3),   # 6:00/km a 145
        _run(24, 8.0, 48, 145, 4),
    ]

    stats, ref_hr = WeeklyEvolutionDigest.build(
        acts, [], TODAY, weeks=2, resting_hr=60, max_hr=188,
    )

    assert ref_hr == 145
    assert stats[0].aerobic_pace_sec == 390   # 6:30
    assert stats[1].aerobic_pace_sec == 360   # 6:00


def test_forma_line_is_the_official_trend():

    acts = [_run(22, 8.0, 48, 145, 1)]

    text = WeeklyEvolutionDigest.render(
        acts, [], TODAY, weeks=2,
        evolution_line="subindo — ~8 s/km mais rápido na mesma FC",
    )

    assert "Forma (a leitura oficial, 8 semanas): subindo" in text


def test_no_runs_renders_nothing():

    assert WeeklyEvolutionDigest.render([], [], TODAY) == ""
