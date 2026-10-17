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


# --- tier-2: body battery ao acordar, respiração, SpO2, carga de vida ---


def test_body_battery_wake_shows_band_not_misleading_arrow():

    # tanque cheio (91) caindo de leve NÃO pode virar "atenção" — banda por nível
    cheio = HealthSnapshotFormatter.panel(
        RecoveryTrend(
            body_battery_wake=91, body_battery_wake_direction=FALLING,
            body_battery_recent=78, days_covered=14,
        )
    )

    assert "Body Battery ao acordar: 91/100 (tanque cheio)" in cheio
    assert "recarga +78/noite" in cheio
    assert "atenção" not in cheio            # nada de susto num tanque cheio

    # acordar no vermelho (nível baixo) = o sinal ruim de verdade
    vermelho = HealthSnapshotFormatter.panel(
        RecoveryTrend(body_battery_wake=22, days_covered=14)
    )

    assert "22/100 (acordou no vermelho)" in vermelho


def test_sleep_respiration_shows_with_attention_when_rising():

    # respiração subindo = pior -> direção FALLING (POV recuperação)
    rec = RecoveryTrend(
        respiration_sleep=17.0, respiration_direction=FALLING, days_covered=14,
    )

    panel = HealthSnapshotFormatter.panel(rec)

    assert "Respiração no sono: 17 rpm ↘️ atenção" in panel


def test_spo2_only_shows_when_sleep_avg_low():

    baixa = HealthSnapshotFormatter.panel(
        RecoveryTrend(spo2_sleep_avg=88, days_covered=14)
    )

    assert "SpO₂ no sono: média 88%" in baixa

    # média de sono normal não polui o painel (aqui, sem outras linhas)
    normal = HealthSnapshotFormatter.panel(
        RecoveryTrend(spo2_sleep_avg=96, hrv_recent=50.0, days_covered=14)
    )

    assert "SpO₂" not in normal


def test_life_load_line():

    rec = RecoveryTrend(
        steps_avg=8500, intensity_minutes_avg=25, days_covered=14,
    )

    panel = HealthSnapshotFormatter.panel(rec)

    assert "Movimento do dia: ~8.500 passos/dia · 25 min intensos/dia" in panel


def _readiness_line(score, level=None):

    rec = RecoveryTrend(
        hrv_recent=50.0, hrv_direction=STABLE, sleep_avg_hours=6.5,
        nights_counted=7, readiness_score=score, readiness_level=level,
        days_covered=14,
    )

    panel = HealthSnapshotFormatter.panel(rec)

    return next(ln for ln in panel.splitlines() if "Prontidão (Garmin)" in ln)


def test_readiness_icon_follows_the_garmin_band_not_a_fixed_check():
    """1/100 nunca leva ✅ (o João recebia 'Prontidão 1/100' com check verde)."""

    assert _readiness_line(1, "POOR").startswith("• 🔴")
    assert _readiness_line(28, "LOW").startswith("• 🟠")
    assert _readiness_line(61, "MODERATE").startswith("• 🟡")
    assert _readiness_line(85, "HIGH").startswith("• ✅")


def test_readiness_icon_falls_back_to_score_bands_without_level():

    assert _readiness_line(2).startswith("• 🔴")
    assert _readiness_line(40).startswith("• 🟠")
    assert _readiness_line(74).startswith("• 🟡")
    assert _readiness_line(90).startswith("• ✅")
