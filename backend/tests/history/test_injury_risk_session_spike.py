"""Risco de lesão pesa o SALTO DE SESSÃO (o melhor preditor) e deixa a razão semanal e a rampa
(preditores fracos) valerem no máximo 1 ponto quando nenhuma corrida foi um salto. Renato 08/11:
ACWR 1,4 + "volume pulou" + recuperação caindo = 3 pontos = ALTO, com o maior treino 3% acima do
maior dos 30 dias."""

from app.application.history.injury_risk_analyzer import InjuryRiskAnalyzer
from app.domain.entities.body_reading import FALLING, STABLE, RecoveryTrend
from app.domain.entities.injury_risk import RISK_ELEVATED, RISK_HIGH, RISK_LOW
from app.domain.entities.training_load import LOAD_CAUTION, TrainingLoad


def _load(long_spike=None, long_km=None, acwr=1.42, weekly=(91.0, 195.0)):

    return TrainingLoad(
        acute_load=195.0, chronic_load=137.0, acwr=acwr, status=LOAD_CAUTION,
        days_of_history=60, weekly_loads=[100.0, 110.0, *weekly],
        long_spike=long_spike, long_run_km=long_km,
    )


FALLING_RECOVERY = RecoveryTrend(hrv_direction=FALLING, rhr_direction=STABLE, days_covered=14)


def test_without_knowing_the_session_the_old_scoring_holds():
    """Sem a leitura de sessão (long_spike None) nada muda: ACWR + rampa + recuperação = ALTO."""

    risk = InjuryRiskAnalyzer.assess(_load(), FALLING_RECOVERY)

    assert risk.level == RISK_HIGH


def test_a_safe_session_caps_the_weekly_proxies_at_one_point():

    risk = InjuryRiskAnalyzer.assess(_load(0.033, (15.5, 15.0)), FALLING_RECOVERY)

    assert risk.level == RISK_ELEVATED and risk.level != RISK_HIGH
    assert any("nenhuma corrida foi salto" in reason for reason in risk.reasons)


def test_a_session_spike_adds_risk_on_its_own():

    risk = InjuryRiskAnalyzer.assess(
        _load(0.25, (18.0, 14.4), acwr=1.0, weekly=(180.0, 190.0)), RecoveryTrend(days_covered=14),
    )

    assert risk.level == RISK_LOW  # um ponto só: sinal, não alarme
    assert any("maior treino da semana" in reason for reason in risk.reasons)


def test_a_huge_session_spike_is_the_worst_signal():

    risk = InjuryRiskAnalyzer.assess(
        _load(1.2, (22.0, 10.0), acwr=1.0, weekly=(180.0, 190.0)), RecoveryTrend(days_covered=14),
    )

    assert risk.level == RISK_ELEVATED
    assert any("120%" in reason for reason in risk.reasons)
