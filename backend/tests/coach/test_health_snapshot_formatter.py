from app.application.coach.writer.health_snapshot_formatter import (
    HealthSnapshotFormatter,
)
from app.domain.entities.body_reading import (
    FALLING,
    RISING,
    STABLE,
    RecoveryTrend,
)


def test_no_data_returns_none():

    assert HealthSnapshotFormatter.panel(RecoveryTrend(days_covered=0)) is None


def test_panel_shows_numbers_and_trends():

    rec = RecoveryTrend(
        hrv_recent=52.0, hrv_direction=RISING,
        rhr_recent=60, rhr_direction=RISING,     # POV recuperação: melhora
        sleep_avg_hours=6.2, short_nights=4, nights_counted=10,
        stress_avg=38, body_battery_recent=18, vo2max=44.0,
        days_covered=14,
    )

    panel = HealthSnapshotFormatter.panel(rec)

    assert "Sua recuperação" in panel
    assert "6h12/noite" in panel
    assert "4 de 10 noites curtas" in panel
    assert "52 ms ↗️ bom sinal" in panel
    assert "60 bpm ↗️ bom sinal" in panel
    assert "Stress médio: 38" in panel
    assert "+18/dia" in panel
    assert "VO₂máx: 44" in panel


def test_falling_trend_shows_attention():

    rec = RecoveryTrend(
        hrv_recent=40.0, hrv_direction=FALLING,
        rhr_recent=64, rhr_direction=FALLING,
        days_covered=14,
    )

    panel = HealthSnapshotFormatter.panel(rec)

    assert "40 ms ↘️ atenção" in panel
    assert "64 bpm ↘️ atenção" in panel


def test_stable_trend_shows_stable():

    rec = RecoveryTrend(
        hrv_recent=48.0, hrv_direction=STABLE, days_covered=14,
    )

    panel = HealthSnapshotFormatter.panel(rec)

    assert "48 ms → estável" in panel


def test_garmin_computed_numbers_are_shown():
    """Quando o relógio computa prontidão/status/nota de sono/HRV status,
    o painel mostra o número da própria Garmin."""

    rec = RecoveryTrend(
        hrv_recent=48.0, hrv_direction=STABLE, hrv_status="BALANCED",
        sleep_avg_hours=7.0, short_nights=0, nights_counted=7, sleep_score=82,
        readiness_score=74, training_status="PRODUCTIVE",
        days_covered=14,
    )

    panel = HealthSnapshotFormatter.panel(rec)

    assert "Prontidão (Garmin): 74/100" in panel
    assert "Status de treino (Garmin): produtivo" in panel
    assert "nota Garmin 82/100" in panel        # colado no sono
    # HRV status descrito como faixa (não "desequilibrado" cru, que soava
    # como defeito do relógio)
    assert "dentro da sua faixa normal (Garmin)" in panel


def test_no_garmin_numbers_on_basic_watch():
    """FR165 (sem prontidão/status): painel segue só com os primitivos."""

    rec = RecoveryTrend(
        hrv_recent=50.0, hrv_direction=RISING,
        sleep_avg_hours=6.5, nights_counted=7,
        days_covered=14,
    )

    panel = HealthSnapshotFormatter.panel(rec)

    assert "Prontidão (Garmin)" not in panel
    assert "Status de treino" not in panel
    assert "nota Garmin" not in panel


def test_only_present_fields_appear():
    """Relógio que não mede body battery/VO2máx: essas linhas somem, sem None."""

    rec = RecoveryTrend(
        sleep_avg_hours=7.0, short_nights=0, nights_counted=7,
        days_covered=7,
    )

    panel = HealthSnapshotFormatter.panel(rec)

    assert "7h00/noite" in panel
    assert "Body Battery" not in panel
    assert "VO₂máx" not in panel
    assert "HRV" not in panel
