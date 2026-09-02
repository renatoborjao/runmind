import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.application.coach.planning.coach_plan_engine import CoachPlanEngine

MODULE = "app.application.coach.planning.coach_plan_engine"
GEN_TEXT = "app.infrastructure.integrations.gemini.client.generate_text"

WEEK_START = date(2026, 7, 6)

# o plano REAL do Renato (gerado por outra IA) como fixture
RENATO_PLAN_JSON = """
{
  "weekly_objective": "ganhar velocidade rumo ao sub-50 sem inflar volume",
  "sessions": [
    {"day": "Monday", "kind": "strength"},
    {"day": "Tuesday", "kind": "run", "workout_type": "Velocidade",
     "distance_km": 9, "pace_min": "4:45", "pace_max": "4:50",
     "structure": "Aquecimento 2 km + 6x800m (rec 400m) + 1,5 km leve",
     "purpose": "aumentar o ritmo de prova"},
    {"day": "Wednesday", "kind": "strength"},
    {"day": "Thursday", "kind": "run", "workout_type": "Rodagem",
     "distance_km": 8, "pace_min": "5:40", "pace_max": "5:55",
     "structure": "8 km + 6 strides de 80m no fim",
     "purpose": "base aeróbica"},
    {"day": "Friday", "kind": "strength"},
    {"day": "Saturday", "kind": "run", "workout_type": "Longão",
     "distance_km": 11, "pace_min": "5:10", "pace_max": "5:45",
     "structure": "8 km a 5:45 + 3 km a 5:10-5:20 (terminar forte)",
     "purpose": "longão progressivo"},
    {"day": "Sunday", "kind": "rest"}
  ]
}
"""


def _generate(response):

    with patch(
        GEN_TEXT,
        new=AsyncMock(return_value=response),
    ):

        return asyncio.run(
            CoachPlanEngine.generate(
                runner_name="Renato",
                objective="10 km sub-50",
                week_start=WEEK_START,
                context="(retrato real do atleta)",
            )
        )


def test_coach_owns_the_phase():
    """A periodização é decisão do COACH: a fase que ele marca no JSON vale."""

    raw = (
        '{"weekly_objective": "construir", "phase": "BUILD", "sessions": '
        '[{"day": "Tuesday", "kind": "run", "workout_type": "Rodagem", '
        '"distance_km": 8, "pace_min": "6:00", "pace_max": "6:30", '
        '"structure": "8 km leve", "purpose": "base"}]}'
    )

    plan = _generate(raw)

    assert plan.phase == "BUILD"


def test_missing_or_invalid_phase_defers_to_fallback():
    """Sem fase válida => 'IA' (o chamador cai no PhaseEngine como rede)."""

    plan = _generate(RENATO_PLAN_JSON)  # fixture não tem "phase"

    assert plan.phase == "IA"


def test_parses_only_the_running_sessions():

    plan = _generate(RENATO_PLAN_JSON)

    assert "sub-50" in plan.weekly_objective

    # SÓ corrida: 3 sessões (ter/qui/sáb). Musculação/descanso descartados.
    assert len(plan.sessions) == 3
    assert plan.running_days == ["Tuesday", "Thursday", "Saturday"]
    assert plan.weekly_volume == 28.0   # 9 + 8 + 11

    # nada de musculação/descanso no plano
    assert plan.find_session_by_day("Monday") is None
    assert plan.find_session_by_day("Sunday") is None

    speed = plan.find_session_by_day("Tuesday")
    assert speed.kind == "run"
    assert speed.planned_distance_km == 9.0
    assert speed.target_pace_min == "4:45"
    assert "6x800" in speed.structure
    assert speed.purpose


def test_structure_as_list_becomes_steps():

    plan_json = (
        '{"weekly_objective": "x", "sessions": [{"day": "Tuesday",'
        ' "kind": "run", "distance_km": 9,'
        ' "structure": ["Aquecimento: 2 km leve",'
        ' "Série: 6x800m a 4:45", "Desaquecimento: 1 km"],'
        ' "purpose": "velocidade"}]}'
    )

    plan = _generate(plan_json)

    steps = plan.find_session_by_day("Tuesday").structure.split("\n")

    assert steps == [
        "Aquecimento: 2 km leve",
        "Série: 6x800m a 4:45",
        "Desaquecimento: 1 km",
    ]


def test_distance_comes_from_steps_not_the_ai_number():
    """Bug do Renato: a IA dá distance_km=6.5 mas os PASSOS somam 7.5 (ela
    esquece as recuperações). A distância gravada tem que ser a dos passos."""

    plan_json = (
        '{"weekly_objective": "x", "sessions": [{"day": "Wednesday",'
        ' "kind": "run", "workout_type": "Intervalado de VO2",'
        ' "distance_km": 6.5,'
        ' "steps": ['
        ' {"kind": "warmup", "distance_m": 2000},'
        ' {"kind": "repeat", "reps": 5, "steps": ['
        '   {"kind": "interval", "distance_m": 600},'
        '   {"kind": "recovery", "distance_m": 200}]},'
        ' {"kind": "cooldown", "distance_m": 1500}],'
        ' "purpose": "vo2"}]}'
    )

    plan = _generate(plan_json)

    assert plan.find_session_by_day("Wednesday").planned_distance_km == 7.5


def test_invalid_json_raises_for_fallback():

    with pytest.raises(ValueError):

        _generate("isto não é json")


def test_plan_without_runs_raises():

    only_strength = '{"sessions": [{"day": "Monday", "kind": "strength"}]}'

    with pytest.raises(ValueError):

        _generate(only_strength)


def test_prompt_carries_the_aversion_directive():

    # o retrato do atleta traz a aversão (via memória): o prompt tem que
    # levar a aversão E a diretriz de COMO honrá-la (manter estímulo).
    captured = {}

    async def _capture(*args, **kwargs):

        captured["contents"] = kwargs.get("contents")

        return RENATO_PLAN_JSON

    with patch(GEN_TEXT, new=AsyncMock(side_effect=_capture)):

        asyncio.run(
            CoachPlanEngine.generate(
                runner_name="Renato",
                objective="10 km sub-50",
                week_start=WEEK_START,
                context=(
                    "Memória do atleta:\n"
                    "- [preferencia] acha tiro na pista chato"
                ),
            )
        )

    prompt = captured["contents"]

    assert "AVERSÕES A TIPO DE TREINO" in prompt
    assert "MANTENHA o estímulo" in prompt
    assert "tiro na pista chato" in prompt


def test_prompt_carries_the_multiple_objectives_directive():

    # a meta pode reunir vários objetivos (saúde + performance): o prompt tem
    # que mandar contemplar TODOS, equilibrando (não virar só máquina de prova)
    captured = {}

    async def _capture(*args, **kwargs):

        captured["contents"] = kwargs.get("contents")

        return RENATO_PLAN_JSON

    with patch(GEN_TEXT, new=AsyncMock(side_effect=_capture)):

        asyncio.run(
            CoachPlanEngine.generate(
                runner_name="Renato",
                objective="saúde e 10 km sub-50",
                week_start=WEEK_START,
                context="Meta: saúde, emagrecer e correr 10 km sub-50.",
            )
        )

    prompt = captured["contents"]

    assert "VÁRIOS OBJETIVOS" in prompt
    assert "CONTEMPLE" in prompt


def test_ai_failure_propagates_for_fallback():

    with patch(
        GEN_TEXT,
        new=AsyncMock(side_effect=RuntimeError("gemini fora do ar")),
    ):

        with pytest.raises(RuntimeError):

            asyncio.run(
                CoachPlanEngine.generate(
                    "Renato", "10k", WEEK_START, "ctx",
                )
            )


def test_session_by_time_carries_duration_not_distance():
    """Sessão por TEMPO: a IA emite duration_min e a sessão fica sem km
    (bug 03/08 — atleta pediu '50 min de rodagem' e virou '8 km')."""

    raw = (
        '{"weekly_objective": "x", "sessions": [{"day": "Tuesday",'
        ' "kind": "run", "workout_type": "Rodagem Moderada",'
        ' "duration_min": 50, "pace_min": "6:00", "pace_max": "6:20",'
        ' "structure": ["50 min em pace moderado"], "purpose": "rodagem"}]}'
    )

    plan = _generate(raw)

    session = plan.sessions[0]

    assert session.planned_duration_minutes == 50
    assert session.planned_distance_km is None
