"""A comparação EXATA bloco-a-bloco depende de distância REAL (GPS). Na esteira
não há GPS — a distância de cada volta vem 0/estimada e o matcher marcaria TODO
bloco como "não completou" (a "análise quebrada" da esteira). O builder NÃO
calcula o veredito exato pra treino indoor: cai no texto livre."""

from unittest.mock import MagicMock, patch

from app.application.coach.context.coach_context_builder import (
    CoachContextBuilder,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_enriched_activity, make_runner

MOD = "app.application.coach.context.coach_context_builder"

_SENTINEL = object()


def _build(indoor: bool):

    executed = make_enriched_activity(indoor=indoor)

    planned = PlannedSession(
        day="Tuesday",
        workout_type="INTERVALADO",
        objective="Tiros",
        planned_distance_km=8.0,
        planned_duration_minutes=None,
        target_pace_min="5:00",
        target_pace_max="5:10",
    )

    assessment = MagicMock(recommended_weekly_volume=30.0, consistency="boa")

    with patch(f"{MOD}.PlannedExecutionMatcher") as matcher:

        matcher.match.return_value = _SENTINEL

        context = CoachContextBuilder.build(
            runner=make_runner(name="Renato"),
            planned=planned,
            executed=executed,
            history=TrainingHistory(activities=[executed.activity]),
            assessment=assessment,
            plan_weekly_volume=30.0,
        )

    return context, matcher


def test_esteira_nao_calcula_comparacao_exata():

    context, matcher = _build(indoor=True)

    assert context.block_comparison is None
    matcher.match.assert_not_called()


def test_outdoor_calcula_comparacao_exata():

    context, matcher = _build(indoor=False)

    assert context.block_comparison is _SENTINEL
    matcher.match.assert_called_once()
