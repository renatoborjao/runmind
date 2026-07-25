from app.application.coach.planning.fitness_directive import (
    fitness_plan_directive,
)
from app.domain.entities.aerobic_efficiency import (
    EFF_DECLINING,
    EFF_IMPROVING,
    EFF_INSUFFICIENT,
    EFF_STABLE,
    AerobicEfficiency,
)


def test_insufficient_is_silent():
    """Sem corridas comparáveis, nada entra no prompt (plano idêntico ao de
    hoje) — mesma cautela da diretriz de corpo."""

    fitness = AerobicEfficiency(direction=EFF_INSUFFICIENT, runs_counted=2)

    assert fitness_plan_directive(fitness) == ""


def test_improving_opens_room_to_progress_gradually():

    fitness = AerobicEfficiency(
        direction=EFF_IMPROVING, runs_counted=8, weeks_covered=8,
    )

    directive = fitness_plan_directive(fitness)

    assert "FORMA AERÓBICA" in directive
    assert "SUBIU" in directive
    assert "evoluir a dose" in directive


def test_stable_suggests_quality_to_break_plateau():

    fitness = AerobicEfficiency(
        direction=EFF_STABLE, runs_counted=8, weeks_covered=8,
    )

    directive = fitness_plan_directive(fitness)

    assert "ESTAGNOU" in directive
    assert "qualidade" in directive
    assert ("tiro" in directive or "limiar" in directive)
    assert "platô" in directive


def test_declining_tells_coach_to_ease():

    fitness = AerobicEfficiency(
        direction=EFF_DECLINING, runs_counted=8, weeks_covered=8,
    )

    directive = fitness_plan_directive(fitness)

    assert "RECUOU" in directive
    assert "base aeróbica" in directive
    assert "Evite SUBIR a intensidade" in directive


def test_directive_is_guidance_not_command():
    """O ponto do Renato: a forma é MAIS UM insumo (soma ao histórico/execução/
    meta), com ajuste GRADUAL — nunca vira o plano de uma semana pra outra."""

    for direction in (EFF_IMPROVING, EFF_STABLE):

        directive = fitness_plan_directive(
            AerobicEfficiency(direction=direction, runs_counted=8, weeks_covered=8)
        )

        assert "mais um insumo" in directive
        assert "histórico" in directive
        assert "GRADUAL" in directive
        assert "não vire o plano de cabeça pra baixo" in directive
        assert "NÃO é ordem" in directive


def test_period_singular_when_one_week():
    """weeks_covered <= 1 vira 'no período' (não '~1 semanas')."""

    fitness = AerobicEfficiency(
        direction=EFF_STABLE, runs_counted=6, weeks_covered=1,
    )

    directive = fitness_plan_directive(fitness)

    assert "no período" in directive
    assert "semanas" not in directive
