"""ÚLTIMA DOSE DE CADA ESTÍMULO (nº 78). O coach via QUANDO cada família foi feita, não a DOSE; sem
saber que o último limiar foi "3,5 km contínuos a 6:15-6:25" não tinha como dar o degrau seguinte
do mesmo estímulo e trocava de família toda semana (fartlek → limiar → VO2), variando sem
progredir. É DADO + conhecimento pro coach decidir (avançar, repetir, trocar, recuar) — nunca cota
nem fórmula."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from app.application.history import stimulus_dose
from app.application.history.stimulus_dose import last_doses, main_lines, render
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_activity

WEEK_1 = date(2026, 10, 5)    # segunda
WEEK_2 = date(2026, 10, 12)
WEEK_3 = date(2026, 10, 19)
TODAY = date(2026, 10, 21)    # quarta da 3ª semana


def _session(day, workout_type, km, structure=""):

    return PlannedSession(
        day=day, workout_type=workout_type, objective="", planned_distance_km=km,
        planned_duration_minutes=None, target_pace_min=None, target_pace_max=None,
        structure=structure,
    )


def _plan(week_start, *sessions):

    return TrainingPlan(
        athlete_name="L", objective="10k", phase="BUILD", weekly_volume=20.0,
        running_days=[s.day for s in sessions], week_start=week_start,
        sessions=list(sessions),
    )


def _run(day: date, km: float, act_id: int):

    return make_activity(
        id=act_id, distance=km * 1000, moving_time=int(km * 380),
        start_date=datetime(day.year, day.month, day.day, 9, tzinfo=UTC),
    )


LIMIAR_1 = (
    "Aquecimento: 2 km leve (7:05-7:35/km)\n"
    "Série: 3x 1,5 km no pace de limiar (6:15-6:25/km)\n"
    "Recuperação: 400m de trote entre as repetições\n"
    "Desaquecimento: 1 km leve\n"
    "Dica: não passe do pace."
)

LIMIAR_2 = (
    "Aquecimento: 2 km leve\n"
    "Série: 4x 1,5 km no pace de limiar (6:12-6:22/km)\n"
    "Recuperação: 300m de trote\n"
    "Desaquecimento: 1 km leve\n"
    "Foco: sustentar o ritmo."
)


def test_the_main_work_is_the_structure_without_warmup_cooldown_tip_and_focus():

    text = main_lines(LIMIAR_1)

    assert text == (
        "Série: 3x 1,5 km no pace de limiar (6:15-6:25/km) · "
        "Recuperação: 400m de trote entre as repetições"
    )
    assert "Aquecimento" not in text and "Dica" not in text and "Desaquecimento" not in text

    assert main_lines("") == "" and main_lines(None) == ""
    assert main_lines("Aquecimento: 2 km\nDica: devagar") == ""


def test_a_long_main_work_is_cut():

    text = main_lines("Série: " + "x" * 400)

    assert len(text) <= 190 and text.endswith("…")


def test_the_last_two_doses_of_a_stimulus_come_latest_first_with_done_or_not():
    """Limiar 3x1,5 km (feito) → 4x1,5 km (não feito): a escada e o que aconteceu."""

    plans = [
        _plan(WEEK_1, _session("Tuesday", "Limiar", 9.0, LIMIAR_1)),
        _plan(WEEK_2, _session("Tuesday", "Limiar", 10.0, LIMIAR_2)),
    ]

    doses = last_doses(plans, [_run(date(2026, 10, 6), 9.0, 1)], TODAY)

    limiar = doses["limiar"]

    assert [(d.day, d.done) for d in limiar] == [
        (date(2026, 10, 13), False), (date(2026, 10, 6), True),
    ]
    assert "4x 1,5 km" in limiar[0].main and "3x 1,5 km" in limiar[1].main


def test_only_stimuli_that_progress_enter_and_only_two_doses_each():

    plans = [
        _plan(WEEK_1, _session("Tuesday", "Limiar", 9.0, LIMIAR_1),
              _session("Thursday", "Rodagem Leve", 6.0, "Corrida: 6 km leve"),
              _session("Saturday", "Longão", 10.0, "Corrida: 10 km contínuos")),
        _plan(WEEK_2, _session("Tuesday", "Limiar", 9.0, LIMIAR_2),
              _session("Saturday", "Longão", 11.0, "Corrida: 11 km contínuos")),
        _plan(WEEK_3, _session("Tuesday", "Limiar", 9.0, LIMIAR_2),
              _session("Saturday", "Longão", 12.0, "Corrida: 12 km contínuos")),
    ]

    runs = [_run(date(2026, 10, 6), 9.0, 1), _run(date(2026, 10, 13), 9.0, 2),
            _run(date(2026, 10, 20), 9.0, 3)]

    doses = last_doses(plans, runs, TODAY)

    # rodagem leve não tem "degrau": não entra
    assert set(doses) == {"limiar", "longão"}

    assert [d.day for d in doses["limiar"]] == [date(2026, 10, 20), date(2026, 10, 13)]

    # o longão de sábado 24/10 é futuro e não foi feito: fora; o de 17/10 e o de 10/10 entram
    assert [d.main for d in doses["longão"]] == [
        "Corrida: 11 km contínuos", "Corrida: 10 km contínuos",
    ]


def test_a_future_session_that_was_not_done_is_left_out_but_one_done_early_counts():

    plan = _plan(WEEK_3, _session("Friday", "Limiar", 9.0, LIMIAR_1))

    assert last_doses([plan], [], TODAY) == {}

    # o limiar de sexta 23/10 feito antes (quarta 21/10): conta
    done_early = _run(date(2026, 10, 21), 9.0, 7)

    with patch(
        "app.application.planner.weekly_plan_matcher.WeeklyPlanMatcher.pairs",
        side_effect=lambda p, runs: [(p.sessions[0], done_early)],
    ):

        doses = last_doses([plan], [done_early], TODAY)

    assert doses["limiar"][0].done is True


def test_sessions_without_a_main_work_or_outside_the_window_are_ignored():

    plans = [
        _plan(date(2026, 7, 6), _session("Tuesday", "Limiar", 9.0, LIMIAR_1)),   # fora das 8 sem
        _plan(WEEK_1, _session("Tuesday", "Limiar", 9.0, "Aquecimento: 2 km")),  # sem dose
    ]

    assert last_doses(plans, [_run(date(2026, 10, 6), 9.0, 1)], TODAY) == {}


def test_the_render_lists_the_ladder_and_carries_the_knowledge_without_making_it_a_rule():

    plans = [
        _plan(WEEK_1, _session("Tuesday", "Limiar", 9.0, LIMIAR_1)),
        _plan(WEEK_2, _session("Tuesday", "Limiar", 10.0, LIMIAR_2)),
    ]

    text = render(last_doses(plans, [_run(date(2026, 10, 6), 9.0, 1)], TODAY), TODAY)

    assert text.startswith("ÚLTIMA DOSE DE CADA ESTÍMULO")
    assert "- limiar: 13/10 (NÃO feito): Série: 4x 1,5 km" in text
    assert " ‖ antes, 06/10 (feito): Série: 3x 1,5 km" in text
    # conhecimento + decisão do coach, nunca cota
    assert "CONHECIMENTO, não regra" in text
    assert "a decisão é sua" in text
    assert "avance a dose, repita (e diga por quê), troque" in text
    assert "diga o que mudou em relação à última dose" in text


def test_without_the_plan_voice_there_is_only_the_data():

    plans = [_plan(WEEK_1, _session("Tuesday", "Limiar", 9.0, LIMIAR_1))]

    doses = last_doses(plans, [_run(date(2026, 10, 6), 9.0, 1)], TODAY)

    text = render(doses, TODAY, plan_voice=False)

    assert "- limiar: 06/10 (feito)" in text and "CONHECIMENTO" not in text

    assert render({}, TODAY) == ""


def test_the_progressive_families_are_the_ones_with_a_ladder():

    names = set(stimulus_dose.PROGRESSIVE)

    assert {"limiar", "VO2 / velocidade", "longão", "ritmo de prova / simulado"} <= names
    assert "rodagem leve / regenerativo" not in names and "acelerações / técnica" not in names

    assert timedelta(weeks=stimulus_dose.WINDOW_WEEKS).days == 56
