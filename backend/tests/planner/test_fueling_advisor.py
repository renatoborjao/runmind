"""Nutrição no treino longo: quando tomar gel (ou derivados) pra repor. O Renato
pediu pro plano dos longões dizer isso. Determinístico (ACSM/ISSN): abaixo de ~75 min
nada; 75–94 min, 1 gel opcional perto da metade; de 95 min, cronograma (a cada ~35 min
a partir do min 35; a cada ~30 acima de 2h30). Caso real: o simulado de 16 km do
Maurício (~100 min) e o longão de 11 km da Fernanda (~72 min, sem nada)."""

from datetime import date
from unittest.mock import patch

import pytest

from app.application.home.week_plan_builder import WeekPlanBuilder  # noqa: F401
from app.application.planner.fueling_advisor import (
    estimated_minutes,
    fueling_lines,
    schedule,
)
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.domain.entities.workout_step import (
    COOLDOWN,
    RUN,
    WARMUP,
    WorkoutStep,
)

REPO = "app.infrastructure.persistence.nutrition_repository.NutritionRepository.load"


def _session(km=10.0, low="6:20", high="6:40", kind="Longão", steps=None, **extra):

    return PlannedSession(
        day="Sunday", workout_type=kind, objective="", planned_distance_km=km,
        planned_duration_minutes=None, target_pace_min=low, target_pace_max=high,
        steps=steps or [], **extra,
    )


def _simulado_16k():
    """O domingo do Maurício: 7 km leves + 6 km no ritmo-alvo + 3 km soltando."""

    return _session(
        km=16.0, low="5:30", high="5:45", kind="Simulado / Longão",
        steps=[
            WorkoutStep(kind=WARMUP, distance_m=7000, pace_min="6:20", pace_max="6:40"),
            WorkoutStep(kind=RUN, distance_m=6000, pace_min="5:30", pace_max="5:45"),
            WorkoutStep(kind=COOLDOWN, distance_m=3000, pace_min="6:30", pace_max="7:00"),
        ],
    )


def _no_restrictions():

    return patch(REPO, return_value={"settings": {}})


# ---- o cronograma -------------------------------------------------------------


@pytest.mark.parametrize(
    "minutes,expected",
    [
        (60, []),
        (74, []),
        (75, [40]),
        (94, [45]),
        (95, [35, 70]),
        (120, [35, 70, 105]),
        (149, [35, 70, 105]),
        (150, [30, 60, 90, 120]),
        (180, [30, 60, 90, 120, 150]),
    ],
)
def test_schedule_by_duration(minutes, expected):

    assert schedule(minutes) == expected


def test_the_last_gel_never_lands_in_the_cooldown():

    for minutes in range(95, 240):

        times = schedule(minutes)

        assert times[-1] <= minutes - 15


# ---- a duração estimada -----------------------------------------------------------


def test_duration_comes_from_the_steps_when_the_plan_has_them():
    """7 km a 6:30 + 6 km a 5:37 + 3 km a 6:45 ≈ 99,5 min — não 16 km × 5:37."""

    assert estimated_minutes(_simulado_16k()) == 100


def test_duration_falls_back_to_distance_times_pace():

    # 11 km a 6:32 de média ≈ 72 min
    assert 70 <= estimated_minutes(_session(km=11.0, low="6:20", high="6:45")) <= 74


def test_duration_without_pace_uses_the_default():

    assert estimated_minutes(_session(km=10.0, low=None, high=None)) == 62


# ---- as linhas ---------------------------------------------------------------------


def test_the_maurício_simulado_gets_a_schedule_and_the_race_rehearsal_note():

    with _no_restrictions():

        lines = fueling_lines(_simulado_16k(), "mauricio")

    assert lines[0] == "Nutrição: gel (~25 g de carboidrato) aos 35 e 70 min, com água"
    assert "Sem gel: 2 balas de goma, 1 banana ou isotônico" in lines[1]
    assert "nunca estreie na prova" in lines[1]
    assert lines[2].startswith("Dica: programe no relógio um alerta de tempo")
    assert "ensaio da prova" in lines[3]
    assert "MESMO gel" in lines[3]


def test_a_regular_long_run_has_no_rehearsal_note():

    with _no_restrictions():

        lines = fueling_lines(_session(km=15.0, kind="Longão Progressivo"), "p")

    assert lines[0].startswith("Nutrição: gel")
    assert all("ensaio" not in line for line in lines)


def test_a_short_long_run_says_nothing():
    """O longão de 11 km da Fernanda (~72 min): repor carboidrato não muda nada."""

    with _no_restrictions():

        assert fueling_lines(_session(km=11.0, low="6:20", high="6:45"), "fernanda") == []
        assert fueling_lines(_session(km=8.0, kind="Rodagem Leve"), "p") == []


def test_between_75_and_94_minutes_it_is_one_optional_gel():

    with _no_restrictions():

        lines = fueling_lines(_session(km=12.5, low="6:20", high="6:40"), "p")

    assert lines[0] == "Nutrição (opcional): 1 gel (~25 g de carboidrato) aos 40 min, com água"


def test_walk_sessions_are_skipped():

    walk = _session(km=14.0, kind="Caminhada")

    walk.kind = "walk"

    with _no_restrictions():

        assert fueling_lines(walk, "p") == []


# ---- restrições da Nutrição -----------------------------------------------------------


def test_diabetes_gets_a_referral_not_a_dose():

    with patch(REPO, return_value={"settings": {"restrictions": "Diabetes tipo 1"}}):

        lines = fueling_lines(_simulado_16k(), "p")

    assert len(lines) == 1
    assert "médico ou nutricionista" in lines[0]
    assert "aos 35" not in lines[0]


def test_someone_who_dislikes_gel_gets_the_same_schedule_with_the_alternatives():

    with patch(REPO, return_value={"settings": {"dislikes": "não curto gel, enjoa"}}):

        lines = fueling_lines(_simulado_16k(), "p")

    assert lines[0].startswith("Nutrição: ~25 g de carboidrato aos 35 e 70 min")
    assert "como você não curte gel" in lines[0]
    assert "2 balas de goma, 1 banana ou isotônico" in lines[0]
    assert all(not line.startswith("Sem gel") for line in lines)


def test_a_failure_reading_the_restrictions_never_blocks_the_advice():

    with patch(REPO, side_effect=OSError("disco")):

        lines = fueling_lines(_simulado_16k(), "p")

    assert lines[0].startswith("Nutrição: gel")


def test_without_a_profile_the_default_advice_applies():

    assert fueling_lines(_simulado_16k(), None)[0].startswith("Nutrição: gel")


# ---- onde o atleta lê: mensagem do plano e app --------------------------------------


def _plan(*sessions) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Mauricio", objective="15k", phase="BUILD", weekly_volume=30.0,
        running_days=[s.day for s in sessions], week_start=date(2026, 10, 19),
        sessions=list(sessions),
    )


def test_the_plan_message_carries_the_nutrition_lines_for_long_sessions_only():

    short = _session(km=8.0, kind="Rodagem Leve")

    short.day = "Friday"

    with _no_restrictions():

        text = "\n".join(
            WeeklyPlanMessageFormatter.session_lines(
                _plan(short, _simulado_16k()), profile="mauricio",
            )
        )

    assert text.count("Nutrição:") == 1
    assert "gel (~25 g de carboidrato) aos 35 e 70 min" in text
    assert "ensaio da prova" in text


def test_the_app_detail_is_the_same_text_as_the_message():

    session = _simulado_16k()

    with _no_restrictions():

        from_app = WeekPlanBuilder._detail(_plan(session), session, "mauricio")
        from_chat = WeeklyPlanMessageFormatter._execution_detail(
            session.workout_type, session, "mauricio",
        )

    assert from_app == from_chat
    assert any(line.startswith("Nutrição: gel") for line in from_app)


def test_a_failure_in_the_advisor_never_breaks_the_workout_detail():

    session = _session(km=14.0)

    with patch(
        "app.application.planner.fueling_advisor.fueling_lines",
        side_effect=RuntimeError("boom"),
    ):

        detail = WeeklyPlanMessageFormatter._execution_detail("LONG_RUN", session)

    assert detail  # o treino segue detalhado, sem a nutrição


def test_the_plan_ai_is_told_not_to_write_its_own_gel_advice():

    from app.application.coach.planning.coach_plan_engine import PROMPT_TEMPLATE

    assert "NUTRIÇÃO NO TREINO LONGO" in PROMPT_TEMPLATE
    assert "o sistema anexa SOZINHO" in PROMPT_TEMPLATE


# ---- a dica do alerta de tempo no relógio ---------------------------------------------
# O Renato queria o ponto do gel "no treino"; esclareceu que NÃO precisa ir no treino
# enviado ao relógio — o plano de domingo e a aba Treino bastam. A dica ensina o recurso
# nativo do Garmin (alerta de tempo recorrente) sem mexer nos passos do treino.


def test_the_tip_teaches_a_recurring_time_alert_that_matches_the_schedule():

    with _no_restrictions():

        lines = fueling_lines(_simulado_16k(), "mauricio")

    tip = next(line for line in lines if line.startswith("Dica:"))

    assert tip == (
        "Dica: programe no relógio um alerta de tempo que repita a cada 35 min "
        "(nos alertas da atividade, opção Tempo) — ele apita na hora do gel"
    )


def test_a_very_long_run_alert_repeats_every_30_minutes():

    steps = [WorkoutStep(kind=RUN, distance_m=24000, pace_min="6:30", pace_max="6:50")]

    with _no_restrictions():

        lines = fueling_lines(_session(km=24.0, steps=steps), "p")

    tip = next(line for line in lines if line.startswith("Dica:"))

    assert "a cada 30 min" in tip


def test_the_optional_single_gel_gets_a_one_time_alert():

    with _no_restrictions():

        lines = fueling_lines(_session(km=12.5, low="6:20", high="6:40"), "p")

    assert (
        "Dica: programe no relógio um alerta de tempo aos 40 min pra lembrar de "
        "tomar o gel"
    ) in lines


def test_someone_who_skips_gel_gets_the_alert_for_replenishing():

    with patch(REPO, return_value={"settings": {"dislikes": "não curto gel"}}):

        lines = fueling_lines(_simulado_16k(), "p")

    tip = next(line for line in lines if line.startswith("Dica:"))

    assert tip.endswith("ele apita na hora de repor")


def test_diabetes_and_short_sessions_get_no_tip():

    with patch(REPO, return_value={"settings": {"restrictions": "diabetes"}}):

        lines = fueling_lines(_simulado_16k(), "p")

    assert all(not line.startswith("Dica:") for line in lines)

    with _no_restrictions():

        assert fueling_lines(_session(km=8.0, kind="Rodagem Leve"), "p") == []


def test_the_workout_sent_to_the_watch_is_untouched_by_the_nutrition_text():
    """Revertido de propósito (nº 62): o treino que sobe pro Garmin segue sem aviso de
    gel nos passos e sem as linhas de nutrição na descrição."""

    from app.application.garmin import garmin_push
    from app.application.garmin.garmin_workout_builder import GarminWorkoutBuilder

    session = _simulado_16k()

    session.structure = "Base 7 km\nBloco 6 km"

    with _no_restrictions():

        description = garmin_push._description(session)

    assert "Nutrição" not in description and "gel" not in description.lower()

    steps = GarminWorkoutBuilder.build(session, "x").workoutSegments[0].workoutSteps

    assert len(steps) == 3
    assert all(s.model_dump().get("description") is None for s in steps)
