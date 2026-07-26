from app.application.coach.intelligence.readiness_evaluator import (
    DEMAND_DEMANDING,
    DEMAND_EASY,
    DEMAND_REST,
    DEMAND_UNKNOWN,
    ReadinessEvaluator,
)
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BALANCED,
    BODY_BUILDING,
    BODY_FRESH,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    FALLING,
    RISING,
    BodyReading,
    RecoveryTrend,
)
from app.domain.entities.readiness_verdict import (
    READINESS_BRAKE,
    READINESS_CAUTION,
    READINESS_GREEN,
    READINESS_NEUTRAL,
)
from app.domain.entities.training_load import TrainingLoad


def _reading(state, recovery=None, limiter="sono") -> BodyReading:

    return BodyReading(
        load=TrainingLoad(
            acute_load=500.0, chronic_load=380.0, acwr=1.31,
            status="CAUTION", days_of_history=28,
        ),
        recovery=recovery or RecoveryTrend(days_covered=14),
        body_state=state,
        limiter=limiter,
    )


def test_strained_freia_e_fala_em_dia_puxado():

    v = ReadinessEvaluator.evaluate(_reading(BODY_STRAINED), DEMAND_DEMANDING)

    assert v.tier == READINESS_BRAKE
    assert v.should_speak is True


def test_strained_nao_fala_em_dia_de_descanso():

    v = ReadinessEvaluator.evaluate(_reading(BODY_STRAINED), DEMAND_REST)

    assert v.tier == READINESS_BRAKE
    assert v.should_speak is False


def test_recovery_flag_so_cutuca_em_dia_puxado():

    puxado = ReadinessEvaluator.evaluate(
        _reading(BODY_RECOVERY_FLAG), DEMAND_DEMANDING
    )
    leve = ReadinessEvaluator.evaluate(
        _reading(BODY_RECOVERY_FLAG), DEMAND_EASY
    )

    assert puxado.tier == leve.tier == READINESS_CAUTION
    assert puxado.should_speak is True
    assert leve.should_speak is False


def test_fresh_da_sinal_verde_so_quando_hoje_e_puxado():

    puxado = ReadinessEvaluator.evaluate(_reading(BODY_FRESH), DEMAND_DEMANDING)
    descanso = ReadinessEvaluator.evaluate(_reading(BODY_FRESH), DEMAND_REST)

    assert puxado.tier == descanso.tier == READINESS_GREEN
    assert puxado.should_speak is True
    assert descanso.should_speak is False


def test_balanced_e_absorbing_ficam_calados():

    for state in (BODY_BALANCED, BODY_ABSORBING):

        v = ReadinessEvaluator.evaluate(_reading(state), DEMAND_DEMANDING)

        assert v.tier == READINESS_NEUTRAL
        assert v.should_speak is False


def test_building_sem_veredito():

    v = ReadinessEvaluator.evaluate(_reading(BODY_BUILDING), DEMAND_DEMANDING)

    assert v.tier == READINESS_NEUTRAL
    assert v.should_speak is False


def test_sem_dado_de_recuperacao_nao_opina():

    reading = _reading(
        BODY_STRAINED, recovery=RecoveryTrend(days_covered=0)
    )

    v = ReadinessEvaluator.evaluate(reading, DEMAND_DEMANDING)

    assert v.tier == READINESS_NEUTRAL
    assert v.should_speak is False


def test_demanda_desconhecida_ainda_freia_no_strained():

    # sem plano casável, uma sobrecarga real ainda merece voz
    v = ReadinessEvaluator.evaluate(_reading(BODY_STRAINED), DEMAND_UNKNOWN)

    assert v.tier == READINESS_BRAKE
    assert v.should_speak is True


def test_reason_carrega_limitador_e_sinais_concretos():

    recovery = RecoveryTrend(
        days_covered=14,
        hrv_recent=42.0, hrv_direction=FALLING,
        rhr_recent=58, rhr_direction=RISING,
        short_nights=6, nights_counted=14,
    )

    v = ReadinessEvaluator.evaluate(
        _reading(BODY_STRAINED, recovery=recovery, limiter="sono"),
        DEMAND_DEMANDING,
    )

    assert "sono" in v.reason
    assert "HRV caindo" in v.reason
    assert "FC de repouso subindo" in v.reason
    assert "6 de 14 noites" in v.reason
