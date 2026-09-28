"""Periodização em BLOCOS e proposta de dia extra (Renato 27/09: "planejar em
bloco" + "o coach deve propor mais um dia de treino, pensando na evolução").
O bloco mora no plano que o abriu; o dia extra é PROPOSTA, nunca adicionado."""

from datetime import date
from unittest.mock import MagicMock

from app.application.coach.planning.ai_plan_service import AIPlanService
from app.application.coach.planning.coach_plan_engine import (
    PROMPT_TEMPLATE,
    CoachPlanEngine,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan

BLOCK = {
    "start": "2026-09-21", "weeks": 4, "focus": "limiar rumo aos 15 km",
    "weeks_plan": ["construir", "construir", "consolidar", "aliviar"],
}


def _plan(week_start, block=None, note=None, label=None):

    return TrainingPlan(
        athlete_name="Renato", objective="x", phase="BUILD", weekly_volume=20,
        running_days=["Tuesday"], week_start=week_start,
        sessions=[PlannedSession("Tuesday", "Limiar", "", 8.0, None, None, None)],
        weekly_objective="Semana de limiar", block=block,
        extra_day_note=note, block_label=label,
    )


def _repo(history, current=None):

    repo = MagicMock()
    repo.history.return_value = history
    repo.load.return_value = current

    return repo


def test_parse_block_keeps_focus_and_the_role_of_each_week():

    block = CoachPlanEngine._parse_block(
        {"focus": "limiar", "weeks_plan": ["a", "b", "c", "d"], "weeks": 9},
    )

    assert block == {"weeks": 4, "focus": "limiar", "weeks_plan": ["a", "b", "c", "d"]}
    assert CoachPlanEngine._parse_block({"focus": "", "weeks_plan": ["a", "b"]}) is None
    assert CoachPlanEngine._parse_block(None) is None


def test_following_weeks_find_the_block_and_their_role():

    repo = _repo([_plan(date(2026, 9, 21), block=BLOCK)])

    block, index = AIPlanService._active_block(repo, "r", date(2026, 9, 28))

    assert index == 2
    line = AIPlanService._block_line((block, index))
    assert "semana 2 de 4" in line and "ESTA semana: construir" in line


def test_a_finished_block_asks_to_open_a_new_one():

    repo = _repo([_plan(date(2026, 9, 21), block=BLOCK)])

    assert AIPlanService._active_block(repo, "r", date(2026, 10, 19)) is None
    assert "ABRE um bloco novo" in AIPlanService._block_line(None)


def test_stamp_starts_a_new_block_this_week_and_labels_it():

    plan = _plan(date(2026, 10, 19), block={k: v for k, v in BLOCK.items() if k != "start"})

    AIPlanService._stamp_block(_repo([]), "r", plan)

    assert plan.block["start"] == "2026-10-19"
    assert plan.block_label == "semana 1 de 4 — limiar rumo aos 15 km"


def test_stamp_labels_a_week_inside_the_running_block():

    plan = _plan(date(2026, 10, 5))

    AIPlanService._stamp_block(_repo([_plan(date(2026, 9, 21), block=BLOCK)]), "r", plan)

    assert plan.block is None
    assert plan.block_label == "semana 3 de 4 — limiar rumo aos 15 km"


def test_message_shows_the_block_and_the_extra_day_proposal():

    text = WeeklyPlanMessageFormatter.format(
        "Renato",
        _plan(
            date(2026, 9, 28), label="semana 2 de 4 — limiar",
            note="Que tal um trote leve de 30 min no domingo?",
        ),
    )

    assert "📦 Bloco: semana 2 de 4 — limiar" in text
    assert "💡 Que tal um trote leve de 30 min no domingo?" in text
    assert "me responde que eu incluo" in text


def test_prompt_proposes_extra_day_but_never_adds_it():

    assert "NUNCA adicione dia" in PROMPT_TEMPLATE
    assert "suggest_extra_day" in PROMPT_TEMPLATE
    assert "PERIODIZAÇÃO EM BLOCOS" in PROMPT_TEMPLATE
