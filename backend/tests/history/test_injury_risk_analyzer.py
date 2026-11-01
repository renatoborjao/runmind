from app.application.history.injury_risk_analyzer import (
    InjuryRiskAnalyzer,
    injury_risk_chat_line,
    injury_risk_directive,
)
from app.domain.entities.body_reading import FALLING, STABLE, RecoveryTrend
from app.domain.entities.injury_risk import (
    RISK_ELEVATED,
    RISK_HIGH,
    RISK_LOW,
)
from app.domain.entities.training_load import LOAD_OPTIMAL, TrainingLoad


def _load(acwr=1.0, weekly=None) -> TrainingLoad:

    return TrainingLoad(
        acute_load=100.0,
        chronic_load=100.0,
        acwr=acwr,
        status=LOAD_OPTIMAL,
        days_of_history=40,
        weekly_loads=weekly or [100.0, 100.0, 100.0, 100.0],
    )


def _recovery(hrv=STABLE, rhr=STABLE) -> RecoveryTrend:

    return RecoveryTrend(
        days_covered=10, hrv_direction=hrv, rhr_direction=rhr,
    )


def test_low_risk_when_everything_calm():

    risk = InjuryRiskAnalyzer.assess(_load(acwr=1.1), _recovery(), [])

    assert risk.level == RISK_LOW
    assert injury_risk_directive(risk) == ""
    assert injury_risk_chat_line(risk) == ""


def test_acwr_spike_alone_is_elevated():
    """ACWR > 1.5 (subiu rápido demais) já vale 2 pontos -> elevado."""

    risk = InjuryRiskAnalyzer.assess(_load(acwr=1.6), _recovery(), [])

    assert risk.level == RISK_ELEVATED
    assert any("ACWR" in r for r in risk.reasons)


def test_spike_plus_falling_recovery_is_high():

    risk = InjuryRiskAnalyzer.assess(
        _load(acwr=1.6), _recovery(hrv=FALLING), [],
    )

    assert risk.level == RISK_HIGH
    assert "prevenção" in injury_risk_directive(risk).lower()


def test_caution_acwr_plus_injury_history_is_elevated():

    risk = InjuryRiskAnalyzer.assess(
        _load(acwr=1.35), _recovery(), ["tendinite no joelho"],
    )

    assert risk.level == RISK_ELEVATED
    assert any("histórico" in r for r in risk.reasons)


def test_volume_ramp_counts():
    """Última semana ≥1.5× a anterior = rampa perigosa."""

    risk = InjuryRiskAnalyzer.assess(
        _load(acwr=1.35, weekly=[80.0, 80.0, 90.0, 140.0]), _recovery(), [],
    )

    # atenção ACWR (+1) + rampa (+1) = elevado
    assert risk.level == RISK_ELEVATED
    assert any("volume pulou" in r for r in risk.reasons)


def test_form_fading_adds_a_risk_factor():
    """Forma quebrando sob fadiga soma 1 ponto; com o ACWR de atenção vira
    risco elevado."""

    risk = InjuryRiskAnalyzer.assess(
        _load(acwr=1.35), _recovery(), [], form_fading=True,
    )

    assert risk.level == RISK_ELEVATED
    assert any("fadiga" in r for r in risk.reasons)


def test_no_acwr_data_does_not_crash():

    risk = InjuryRiskAnalyzer.assess(_load(acwr=None), _recovery(), None)

    assert risk.level == RISK_LOW


def test_chat_line_present_when_elevated():

    risk = InjuryRiskAnalyzer.assess(_load(acwr=1.6), _recovery(), [])

    line = injury_risk_chat_line(risk)

    assert line.startswith("- Risco de lesão")
    assert "elevado" in line


def test_coming_back_from_a_weak_week_is_not_a_ramp():
    """Renato 01/11: 46 → 156 min (a semana fraca era a chuva) com a recuperação caindo somava
    "rampa" + recuperação = risco ELEVADO e o coach cortou o treino forte. Com o rebote
    reconhecido pelo analisador da carga (a semana é 77% do que ele sustentava) a rampa não conta."""

    spiky = [380.0, 480.0, 163.0, 590.0]

    ramp = TrainingLoad(
        acute_load=590.0, chronic_load=766.0, acwr=0.77, status=LOAD_OPTIMAL,
        days_of_history=22, weekly_loads=spiky, rebound=(202.0, 156.0),
    )

    risk = InjuryRiskAnalyzer.assess(ramp, _recovery(hrv=FALLING), [])

    assert risk.level == RISK_LOW
    assert not any("pulou" in r for r in risk.reasons)

    no_rebound = TrainingLoad(
        acute_load=590.0, chronic_load=766.0, acwr=0.77, status=LOAD_OPTIMAL,
        days_of_history=22, weekly_loads=spiky,
    )

    assert any(
        "pulou" in r
        for r in InjuryRiskAnalyzer.assess(no_rebound, _recovery(hrv=FALLING), []).reasons
    )
