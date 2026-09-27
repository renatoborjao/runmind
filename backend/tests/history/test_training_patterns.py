from datetime import date, datetime, timedelta, timezone

from app.application.history.training_patterns import TrainingPatterns
from app.domain.entities.body_reading_snapshot import BodyReadingSnapshot
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_activity

TODAY = date(2026, 9, 26)  # sábado
WEEK = date(2026, 9, 21)


def _snap(day: date, state="RECOVERY_FLAG", rhr=70, hrv=46, sleep=6.3):
    return BodyReadingSnapshot(
        at=f"{day.isoformat()}T05:00:00-03:00", body_state=state,
        limiter="sono", acwr=0.76, acwr_status="DETRAINING", hrv_recent=hrv,
        hrv_direction="falling", rhr_recent=rhr, rhr_direction="falling",
        sleep_avg_hours=sleep, short_nights=6, nights_counted=14,
    )


def test_recovery_drift_flags_real_worsening_vs_own_baseline():
    """Caso real renato2: FC de repouso 59→70 e HRV 60→46 com 13 leituras em
    alerta = PIORA real (não o baseline dele) — o plano não pode empurrar."""

    base = [_snap(TODAY - timedelta(days=40 - i), "BALANCED", 59, 60) for i in range(5)]
    recent = [_snap(TODAY - timedelta(days=2 - i)) for i in range(3)]

    drift = TrainingPatterns.recovery_drift(base + recent)

    assert drift.alert_streak == 3
    assert drift.rhr_base == 59 and drift.rhr_now == 70
    assert drift.worsening is True


def test_stable_alert_is_not_worsening():
    """Alerta crônico no MESMO patamar da base (o normal dele) não é piora —
    não trava a progressão à toa."""

    base = [_snap(TODAY - timedelta(days=40 - i), "RECOVERY_FLAG", 55, 40) for i in range(5)]
    recent = [_snap(TODAY - timedelta(days=2 - i), rhr=56, hrv=39) for i in range(3)]

    assert TrainingPatterns.recovery_drift(base + recent).worsening is False


def _plan(sessions):
    return TrainingPlan(
        athlete_name="R", objective="15k", phase="BUILD", weekly_volume=30,
        running_days=[d for d, *_ in sessions], week_start=WEEK,
        sessions=[
            PlannedSession(d, t, "", km, mins, None, None)
            for d, t, km, mins in sessions
        ],
    )


def _run(day: date, km: float, minutes: float, hr: int, act_id: int):
    return make_activity(
        id=act_id,
        start_date=datetime(day.year, day.month, day.day, 9, tzinfo=timezone.utc),
        distance=km * 1000, moving_time=int(minutes * 60), average_heartrate=hr,
    )


def test_easy_too_hard_overshoot_and_cut_short():

    plan = _plan([
        ("Tuesday", "Rodagem Leve", None, 45),
        ("Thursday", "Rodagem Leve", 8.0, None),
        ("Saturday", "Longão", 14.0, None),
    ])

    runs = [
        _run(WEEK + timedelta(days=1), 8.5, 54, 144, 1),   # +20% no leve
        _run(WEEK + timedelta(days=3), 8.0, 50, 156, 2),   # leve em 156 (> 151)
        _run(WEEK + timedelta(days=5), 11.0, 70, 150, 3),  # longão 79% do plano
    ]

    text = TrainingPatterns.render([plan], runs, [], [], TODAY, ceiling=151)

    assert "Aderência: fez 3 de 3" in text
    assert "saindo FORTE: 1 de 3" in text and "24/09 (156 bpm)" in text
    assert "Passou do combinado em dia LEVE: 22/09 (+20%)" in text
    assert "Encurtou sessão importante: 26/09 Longão (79%)" in text


def test_no_ceiling_no_easy_judgement():
    """Sem régua de FC confiável (sem repouso), não julga 'leve forte' —
    melhor não cobrar do que cobrar com régua errada."""

    plan = _plan([("Tuesday", "Rodagem Leve", 8.0, None)])

    runs = [_run(WEEK + timedelta(days=1), 8.0, 50, 170, 1)]

    text = TrainingPatterns.render([plan], runs, [], [], TODAY, ceiling=None)

    assert "FORTE" not in text and "no controle" not in text


def test_aerobic_ceiling_by_heart_rate_reserve():

    # renato2: máx 188, repouso 66 → 66 + 0.7 × 122 = 151
    assert TrainingPatterns.aerobic_ceiling(188, 66) == 151
    assert TrainingPatterns.aerobic_ceiling(188, None) is None


def test_week_volume_far_above_plan_is_a_pattern():
    """Maurício real: semana planejada em ~28 km, executou 43 (+53%)."""

    prev = TrainingPlan(
        athlete_name="M", objective="15k", phase="BUILD", weekly_volume=28,
        running_days=["Tuesday"], week_start=date(2026, 9, 14),
        sessions=[PlannedSession("Tuesday", "Rodagem", "", 8.0, None, None, None)],
    )

    runs = [
        _run(date(2026, 9, 14) + timedelta(days=d), km, 60, 140, i)
        for i, (d, km) in enumerate([(1, 12.0), (3, 11.0), (5, 20.0)], start=1)
    ]

    text = TrainingPatterns.render([prev], runs, [], [], TODAY)

    assert "Volume da semana × plano: 14/09 plano ~28 → fez 43 km (+54%)" in text


def test_long_run_done_longer_on_another_day_is_not_a_miss():
    """Fernanda real: longão de 8,5 km planejado no DOMINGO, correu 13,6 km no
    SÁBADO. Antes: 'furou o longão' + corrida extra. Agora é o longão feito —
    maior que o combinado (o que a análise cobra), não um furo."""

    plan = _plan([
        ("Tuesday", "Rodagem Leve", 4.0, None),
        ("Sunday", "Longão Progressivo", 8.5, None),
    ])

    runs = [
        _run(WEEK + timedelta(days=1), 4.0, 25, 135, 1),    # terça
        _run(WEEK + timedelta(days=5), 13.6, 85, 140, 2),   # sábado (26/09)
    ]

    text = TrainingPatterns.render([plan], runs, [], [], TODAY, ceiling=146)

    assert "Aderência: fez 2 de 2" in text
    assert "furou" not in text
