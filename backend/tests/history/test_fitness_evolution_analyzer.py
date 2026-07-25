from datetime import date, datetime, timedelta

from app.application.history.aerobic_efficiency_analyzer import (
    AerobicEfficiencyAnalyzer,
)
from app.application.history.fitness_evolution_analyzer import (
    FitnessEvolutionAnalyzer,
)
from app.domain.entities.aerobic_efficiency import (
    EFF_IMPROVING,
    AerobicEfficiency,
)
from app.domain.entities.daily_health import DailyHealth
from app.domain.entities.fitness_evolution import (
    EVO_CLEAR,
    EVO_IMPROVING,
    EVO_INSUFFICIENT,
    EVO_MIXED,
    EVO_STABLE,
)
from app.domain.entities.signal_trend import (
    CONF_CLEAR,
    TREND_DECLINING,
    TREND_IMPROVING,
    SignalTrend,
)
from tests.coach.factories import make_activity

REF = date(2026, 7, 25)


def _trend(direction, clear=True):

    return SignalTrend(
        direction=direction,
        confidence=CONF_CLEAR if clear else "MARGINAL",
        points=8, span_days=40, span_weeks=6,
        relative_change=0.05 if direction == TREND_IMPROVING else -0.05,
        per_week=0.1, r_squared=0.6,
        recent_value=45.0, earlier_value=43.0, mean_value=44.0,
    )


# -- combinação (o coração da triangulação) ---------------------------

def test_ef_alone_drives_verdict_marginal():
    ef = AerobicEfficiency(direction=EFF_IMPROVING, runs_counted=8, weeks_covered=8)

    direction, confidence = FitnessEvolutionAnalyzer._combine(ef, None, None, None)

    assert direction == EVO_IMPROVING
    assert confidence != EVO_CLEAR      # um sinal só, sem corroboração


def test_two_signals_agreeing_are_clear():
    ef = AerobicEfficiency(direction=EFF_IMPROVING, runs_counted=8, weeks_covered=8)

    direction, confidence = FitnessEvolutionAnalyzer._combine(
        ef, None, _trend(TREND_IMPROVING), None
    )

    assert direction == EVO_IMPROVING
    assert confidence == EVO_CLEAR


def test_long_ef_corroborates_short_into_clear():
    """EF curto + EF longo (claro) na mesma direção elevam a confiança —
    a melhora se sustenta em dois horizontes."""

    ef = AerobicEfficiency(direction=EFF_IMPROVING, runs_counted=8, weeks_covered=8)

    _, confidence = FitnessEvolutionAnalyzer._combine(
        ef, _trend(TREND_IMPROVING), None, None
    )

    assert confidence == EVO_CLEAR


def test_conflicting_signals_are_mixed():
    ef = AerobicEfficiency(direction=EFF_IMPROVING, runs_counted=8, weeks_covered=8)

    direction, confidence = FitnessEvolutionAnalyzer._combine(
        ef, None, _trend(TREND_DECLINING), None
    )

    assert confidence == EVO_MIXED


def test_resting_hr_alone_is_too_weak_to_claim_evolution():
    """FC-repouso é sinal de APOIO — sozinho não decreta 'melhorando'."""

    direction, _ = FitnessEvolutionAnalyzer._combine(
        None, None, None, _trend(TREND_IMPROVING)
    )

    assert direction == EVO_STABLE


def test_no_signals_is_insufficient():

    direction, _ = FitnessEvolutionAnalyzer._combine(
        AerobicEfficiency(), None, None, None
    )

    assert direction == EVO_INSUFFICIENT


# -- normalização de calor --------------------------------------------

def test_heat_normalization_lifts_hot_run_ef():
    """Mesmo pace e FC, mas quente: o EF normalizado sobe (a FC 'quente' é
    descontada), então um treino quente não parece perda de forma."""

    cool = AerobicEfficiencyAnalyzer._heat_normalized_hr(150, 15)   # na ref
    hot = AerobicEfficiencyAnalyzer._heat_normalized_hr(150, 30)    # +15°C

    assert cool == 150
    assert hot < 150                       # FC descontada
    assert 150 - hot <= 8                  # respeita o teto


def test_no_temp_leaves_hr_untouched():

    assert AerobicEfficiencyAnalyzer._heat_normalized_hr(150, None) == 150
    assert AerobicEfficiencyAnalyzer._heat_normalized_hr(150, 10) == 150  # frio


# -- degradação graciosa (integração) ---------------------------------

def _rising_runs():
    """8 corridas semanais, velocidade subindo com FC constante → EF sobe."""

    runs = []

    for i in range(8):

        runs.append(
            make_activity(
                id=1000 + i,
                start_date=datetime(2026, 6, 1, 7) + timedelta(days=i * 7),
                distance=10000.0,
                average_speed=3.20 + i * 0.03,
                average_heartrate=150.0,
            )
        )

    return runs


def test_analyze_degrades_to_ef_when_health_is_empty():
    """Sem saúde (recém-conectada), VO₂máx/FC-repouso abstêm e o EF carrega."""

    evo = FitnessEvolutionAnalyzer.analyze(
        _rising_runs(), health_series=[], reference_date=REF,
    )

    assert evo.has_data
    assert evo.ef is not None
    assert evo.vo2max is None
    assert evo.rhr is None
    assert evo.direction == EVO_IMPROVING


def test_thin_health_series_abstains():
    """Poucos dias de VO₂máx não viram tendência (não inventa sinal)."""

    series = [
        DailyHealth(date=(REF - timedelta(days=d)).isoformat(), vo2max=44.0)
        for d in range(3)      # 3 dias só
    ]

    evo = FitnessEvolutionAnalyzer.analyze(
        _rising_runs(), health_series=series, reference_date=REF,
    )

    assert evo.vo2max is None
