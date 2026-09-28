"""Escolha LIVRE pela evolução (Renato 27/09: "o coach está sempre preso nos
mesmos tipos... nada chumbado"). A instrução antiga mandava girar só o dia forte
entre tempo/fartlek/progressivo; o leve e o longão ficavam iguais toda semana.
E subida fica fora do plano da semana — só no avulso, quando o atleta pede."""

from datetime import date

from app.application.coach.planning.coach_plan_engine import PROMPT_TEMPLATE
from app.application.coach.planning.plan_context_builder import (
    PlanContextBuilder,
)
from app.application.coach.planning.workout_menu import ONE_OFF_MENU, WORKOUT_MENU
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan


def _plan(week_start, types):

    days = ["Tuesday", "Thursday", "Saturday"]

    return TrainingPlan(
        athlete_name="R", objective="x", phase="BUILD", weekly_volume=0,
        running_days=days, week_start=week_start,
        sessions=[
            PlannedSession(d, t, "", 8.0, None, None, None)
            for d, t in zip(days, types)
        ],
    )


def test_recent_weeks_show_the_whole_week_without_narrowing_the_choice():

    line = PlanContextBuilder._recent_types_line([
        _plan(date(2026, 9, 14), ["Fartlek", "Rodagem Leve", "Longão"]),
        _plan(date(2026, 9, 21), ["Limiar", "Rodagem Leve", "Longão"]),
    ])

    assert "ter Fartlek · qui Rodagem Leve · sáb Longão" in line
    assert "SEMANA INTEIRA" in line and "LIVRE" in line
    assert "tempo/limiar, fartlek ou progressivo" not in line


def test_plan_prompt_chooses_by_evolution_for_every_session():

    assert "EVOLUÇÃO É O CRITÉRIO DE ESCOLHA" in PROMPT_TEMPLATE
    assert "semana INTEIRA" in PROMPT_TEMPLATE


def test_hills_are_only_offered_as_one_off():

    assert "Kenyan" not in WORKOUT_MENU and "Subida / tiros em rampa" not in WORKOUT_MENU
    assert "Kenyan" in ONE_OFF_MENU
