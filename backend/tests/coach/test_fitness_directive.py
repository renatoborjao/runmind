from app.application.coach.planning.fitness_directive import (
    fitness_plan_directive,
)
from app.domain.entities.aerobic_efficiency import AerobicEfficiency
from app.domain.entities.fitness_evolution import (
    EVO_DECLINING,
    EVO_IMPROVING,
    EVO_INSUFFICIENT,
    EVO_STABLE,
    FitnessEvolution,
)
from app.domain.entities.signal_trend import (
    CONF_CLEAR,
    TREND_IMPROVING,
    SignalTrend,
)


def _evo(direction, weeks=8, vo2max=None, rhr=None):
    """FitnessEvolution com um EF só pra carregar o período."""

    ef = (
        AerobicEfficiency(direction="STABLE", runs_counted=8, weeks_covered=weeks)
        if direction != EVO_INSUFFICIENT
        else None
    )

    return FitnessEvolution(
        direction=direction,
        ef=ef,
        vo2max=vo2max,
        rhr=rhr,
    )


def _trend(direction):

    return SignalTrend(
        direction=direction, confidence=CONF_CLEAR, points=8, span_days=40,
        span_weeks=6, relative_change=0.05, per_week=0.1, r_squared=0.6,
        recent_value=45.0, earlier_value=43.0, mean_value=44.0,
    )


def test_insufficient_is_silent():
    """Sem sinal com lastro, nada entra no prompt (plano idêntico ao de hoje)."""

    assert fitness_plan_directive(_evo(EVO_INSUFFICIENT)) == ""


def test_improving_opens_room_to_progress_gradually():

    directive = fitness_plan_directive(_evo(EVO_IMPROVING))

    assert "FORMA" in directive
    assert "SUBIU" in directive
    assert "evoluir a dose" in directive


def test_stable_suggests_quality_to_break_plateau():

    directive = fitness_plan_directive(_evo(EVO_STABLE))

    assert "ESTAGNOU" in directive
    assert "qualidade" in directive
    assert ("tiro" in directive or "limiar" in directive)
    assert "platô" in directive


def test_declining_tells_coach_to_ease():

    directive = fitness_plan_directive(_evo(EVO_DECLINING))

    assert "RECUOU" in directive
    assert "base aeróbica" in directive
    assert "Evite SUBIR a intensidade" in directive


def test_directive_is_guidance_not_command():
    """O ponto do Renato: a forma é MAIS UM insumo (soma ao histórico/execução/
    meta), com ajuste GRADUAL — nunca vira o plano de uma semana pra outra."""

    for direction in (EVO_IMPROVING, EVO_STABLE):

        directive = fitness_plan_directive(_evo(direction))

        assert "mais um insumo" in directive
        assert "histórico" in directive
        assert "GRADUAL" in directive
        assert "não vire o plano de cabeça pra baixo" in directive
        assert "NÃO é ordem" in directive


def test_period_singular_when_one_week():
    """EF com weeks_covered <= 1 vira 'no período' (não '~1 semanas')."""

    directive = fitness_plan_directive(_evo(EVO_STABLE, weeks=1))

    assert "no período" in directive


def test_corroboration_cites_supporting_signals():
    """Quando VO₂máx confirma, a diretriz cita — dá confiança à IA."""

    directive = fitness_plan_directive(
        _evo(EVO_IMPROVING, vo2max=_trend(TREND_IMPROVING))
    )

    assert "corroborado por VO₂máx" in directive
