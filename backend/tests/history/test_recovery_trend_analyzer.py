from app.application.history.recovery_trend_analyzer import (
    RecoveryTrendAnalyzer,
)
from app.domain.entities.body_reading import FALLING, RISING, STABLE
from app.domain.entities.daily_health import DailyHealth


def _series(hrv=None, rhr=None, sleep=None):

    n = max(len(x) for x in (hrv, rhr, sleep) if x) if any((hrv, rhr, sleep)) else 0

    out = []

    for i in range(n):

        out.append(
            DailyHealth(
                date=f"2026-07-{i + 1:02d}",
                hrv_weekly_avg=hrv[i] if hrv else None,
                resting_hr=rhr[i] if rhr else None,
                sleep_hours=sleep[i] if sleep else None,
            )
        )

    return out


def test_rising_hrv_is_detected():

    trend = RecoveryTrendAnalyzer.analyze(
        _series(hrv=[40, 41, 42, 43, 48, 49, 50, 51])
    )

    assert trend.hrv_direction == RISING
    assert trend.hrv_recent == 51


def test_reference_date_ignores_days_after_it():
    """Leitura de uma semana PASSADA (backfill/trajetória): dias posteriores à
    referência não entram — o corpo de hoje não contamina o retrato de então."""

    from datetime import date

    # HRV sobe forte só nos últimos dias (07 e 08); cortando em 06/07, a
    # série vista é plana e o recente disponível é o do dia 06.
    series = _series(hrv=[40, 40, 40, 40, 40, 41, 60, 61])

    trend = RecoveryTrendAnalyzer.analyze(
        series, reference_date=date(2026, 7, 6)
    )

    assert trend.hrv_recent == 41         # dia 06, não o 61 do dia 08
    assert trend.days_covered == 6        # só os 6 primeiros dias


def test_falling_resting_hr_reads_as_recovery_improving():

    # FC de repouso caindo (66->60) = recuperação MELHORANDO -> RISING (POV rec)
    trend = RecoveryTrendAnalyzer.analyze(
        _series(rhr=[66, 66, 65, 65, 60, 60, 60, 60])
    )

    assert trend.rhr_direction == RISING


def test_falling_hrv_is_flagged():

    trend = RecoveryTrendAnalyzer.analyze(
        _series(hrv=[52, 51, 50, 49, 44, 43, 42, 40])
    )

    assert trend.hrv_direction == FALLING


def test_too_few_points_stays_stable():

    trend = RecoveryTrendAnalyzer.analyze(_series(hrv=[40, 55]))

    assert trend.hrv_direction == STABLE


def test_sleep_avg_and_short_nights():

    trend = RecoveryTrendAnalyzer.analyze(
        _series(sleep=[4.0, 4.5, 5.0, 7.5, 8.0, 6.2])
    )

    # 3 noites < 6h (4.0, 4.5, 5.0)
    assert trend.short_nights == 3
    assert trend.nights_counted == 6
    assert trend.sleep_avg_hours == round(sum([4.0, 4.5, 5.0, 7.5, 8.0, 6.2]) / 6, 1)


def test_empty_series_has_no_data():

    trend = RecoveryTrendAnalyzer.analyze([])

    assert trend.has_data is False
    assert trend.days_covered == 0


def test_garmin_computed_scores_are_carried():
    """Os números que a própria Garmin calcula (relógio melhor) chegam à
    RecoveryTrend, pegando o mais recente da janela."""

    series = [
        DailyHealth(
            date="2026-07-01", resting_hr=55,
            readiness_score=60, training_status="MAINTAINING",
            hrv_status="BALANCED", sleep_score=70,
        ),
        DailyHealth(
            date="2026-07-02", resting_hr=54,
            readiness_score=74, training_status="PRODUCTIVE",
            hrv_status="BALANCED", sleep_score=82,
        ),
    ]

    trend = RecoveryTrendAnalyzer.analyze(series)

    # o mais recente da janela manda
    assert trend.readiness_score == 74
    assert trend.training_status == "PRODUCTIVE"
    assert trend.hrv_status == "BALANCED"
    assert trend.sleep_score == 82


def test_basic_watch_leaves_garmin_scores_none():
    """FR165: sem prontidão/status computados -> None (cai no derivado)."""

    trend = RecoveryTrendAnalyzer.analyze(
        _series(hrv=[40, 42, 44, 46], rhr=[56, 55, 54, 53])
    )

    assert trend.readiness_score is None
    assert trend.training_status is None
    assert trend.sleep_score is None


# --- tier-2: body battery ao acordar, respiração, SpO2, carga de vida ---


def _tier2_series(wake=None, resp=None, spo2_sleep=None, steps=None,
                  im_mod=None, im_vig=None, active_cal=None):

    cols = (wake, resp, spo2_sleep, steps, im_mod, im_vig, active_cal)

    n = max((len(x) for x in cols if x), default=0)

    out = []

    for i in range(n):

        out.append(
            DailyHealth(
                date=f"2026-07-{i + 1:02d}",
                body_battery_at_wake=wake[i] if wake else None,
                respiration_sleep_avg=resp[i] if resp else None,
                spo2_sleep_avg=spo2_sleep[i] if spo2_sleep else None,
                steps=steps[i] if steps else None,
                intensity_minutes_moderate=im_mod[i] if im_mod else None,
                intensity_minutes_vigorous=im_vig[i] if im_vig else None,
                active_calories=active_cal[i] if active_cal else None,
            )
        )

    return out


def test_body_battery_wake_recent_and_direction():
    # tanque ao acordar caindo (60->35) = recuperação PIORANDO -> FALLING
    trend = RecoveryTrendAnalyzer.analyze(
        _tier2_series(wake=[62, 60, 58, 56, 40, 38, 36, 35])
    )

    assert trend.body_battery_wake == 35
    assert trend.body_battery_wake_direction == FALLING


def test_body_battery_wake_rising_is_recovery_improving():
    trend = RecoveryTrendAnalyzer.analyze(
        _tier2_series(wake=[30, 32, 34, 36, 50, 52, 54, 56])
    )

    assert trend.body_battery_wake_direction == RISING


def test_sleep_respiration_rising_reads_as_worsening():
    # respiração no sono SUBINDO (13->17) = pior -> FALLING (POV recuperação)
    trend = RecoveryTrendAnalyzer.analyze(
        _tier2_series(resp=[13.0, 13.0, 13.2, 13.4, 16.5, 16.8, 17.0, 17.2])
    )

    assert trend.respiration_sleep == 17.2
    assert trend.respiration_direction == FALLING


def test_life_load_averages_and_spo2_sleep():
    trend = RecoveryTrendAnalyzer.analyze(
        _tier2_series(
            spo2_sleep=[95, 94, 96, 88],
            steps=[10000, 12000, 14000, 16000],
            im_mod=[10, 20, 0, 30],
            im_vig=[5, 0, 10, 5],
            active_cal=[300, 400, 500, 600],
        )
    )

    assert trend.spo2_sleep_avg == 88                 # o mais recente
    assert trend.steps_avg == 13000                   # média
    assert trend.active_calories_avg == 450
    # (mod + 2×vig)/dia: (20,20,20,40) -> média 25
    assert trend.intensity_minutes_avg == 25


def test_tier2_absent_stays_none():
    trend = RecoveryTrendAnalyzer.analyze(
        _series(hrv=[40, 42, 44, 46])
    )

    assert trend.body_battery_wake is None
    assert trend.body_battery_wake_direction == STABLE
    assert trend.respiration_sleep is None
    assert trend.spo2_sleep_avg is None
    assert trend.steps_avg is None
    assert trend.intensity_minutes_avg is None
