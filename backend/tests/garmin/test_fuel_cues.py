"""O AVISO DO GEL dentro do treino do relógio. Pedido do Renato ("seria legal no
treino também informar esse ponto do gel"): o longão sobe pro Garmin com um passo
curto (15 s, mesmo pace) e a nota "GEL agora" no minuto certo. Caso real — o
simulado de 16 km do Maurício (7 km leves + 6 km no ritmo-alvo + 3 km soltando, ~100
min): gel aos 35 e 70 min. A geometria do treino não pode mudar, os tiros não podem
ser tocados e, se o Garmin recusar, o treino sobe sem os avisos."""

from datetime import date
from unittest.mock import MagicMock, patch

from app.application.garmin.fuel_cues import (
    CUE_SECONDS,
    CueStep,
    insert_fuel_cues,
)
from app.application.garmin.garmin_push import push_session
from app.application.garmin.garmin_workout_builder import GarminWorkoutBuilder
from app.core.config import Settings
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.workout_step import (
    COOLDOWN,
    INTERVAL,
    RECOVERY,
    REPEAT,
    RUN,
    WARMUP,
    WorkoutStep,
)

PUSH = "app.application.garmin.garmin_push"
REPO = "app.infrastructure.persistence.nutrition_repository.NutritionRepository.load"


def _simulado_steps():

    return [
        WorkoutStep(kind=WARMUP, distance_m=7000, pace_min="6:20", pace_max="6:40"),
        WorkoutStep(kind=RUN, distance_m=6000, pace_min="5:30", pace_max="5:45"),
        WorkoutStep(kind=COOLDOWN, distance_m=3000, pace_min="6:30", pace_max="7:00"),
    ]


def _session(steps=None, km=16.0, kind="Simulado / Longão"):

    return PlannedSession(
        day="Sunday", workout_type=kind, objective="Ensaio da prova",
        planned_distance_km=km, planned_duration_minutes=None,
        target_pace_min="5:30", target_pace_max="5:45",
        steps=_simulado_steps() if steps is None else steps,
        structure="Base 7 km\nBloco 6 km\nSoltar 3 km",
        purpose="Ensaio da prova",
    )


def _meters(steps):

    return sum(s.distance_m or 0 for s in steps if not isinstance(s, CueStep))


def _cues(steps):

    return [s for s in steps if isinstance(s, CueStep)]


# ---- a regra de colocar os avisos ----------------------------------------------------


def test_the_mauricio_simulado_gets_two_cues_at_the_right_places():

    out = insert_fuel_cues(_simulado_steps(), [35, 70], session_pace=5.625)

    cues = _cues(out)

    assert [c.note for c in cues] == [
        "GEL agora (1 de 2) - com água",
        "GEL agora (2 de 2) - com água",
    ]
    assert all(c.duration_sec == CUE_SECONDS for c in cues)

    # 1º gel cai no passo leve (0–45 min), 2º no bloco do ritmo-alvo (45–79 min)
    assert out.index(cues[0]) < 3 and out.index(cues[1]) > out.index(cues[0])

    # cada aviso herda o pace do passo em que cai (o relógio não troca de alvo)
    assert (cues[0].pace_min, cues[0].pace_max) == ("6:20", "6:40")
    assert (cues[1].pace_min, cues[1].pace_max) == ("5:30", "5:45")
    assert cues[0].kind == WARMUP and cues[1].kind == RUN


def test_the_geometry_of_the_workout_does_not_change():
    """A soma de km é a mesma (menos os ~40 m que cada aviso de 15 s gasta)."""

    out = insert_fuel_cues(_simulado_steps(), [35, 70], session_pace=5.625)

    assert abs(_meters(out) - 16000) <= 2 * 15 * 3  # 2 avisos × 15 s a ~3 m/s

    # o bloco do ritmo-alvo continua com 6 km no total, só dividido em dois pedaços
    block = [s for s in out if s.kind == RUN and not isinstance(s, CueStep)]

    assert abs(sum(s.distance_m for s in block) - 6000) <= 60

    # aquecimento e desaquecimento idem
    assert abs(sum(s.distance_m for s in out if s.kind == COOLDOWN) - 3000) < 1


def test_first_cue_cuts_the_warmup_where_35_minutes_of_planned_pace_land():

    out = insert_fuel_cues(_simulado_steps(), [35, 70], session_pace=5.625)

    first = out[0]

    # 35 min a 6:30/km = 5,38 km (arredondado a 50 m)
    assert first.kind == WARMUP
    assert first.duration_sec is None
    assert 5300 <= first.distance_m <= 5450


def test_no_times_no_change():

    steps = _simulado_steps()

    assert insert_fuel_cues(steps, []) == steps
    assert insert_fuel_cues([], [35]) == []


def test_a_time_based_step_is_cut_by_time_and_keeps_its_total():

    steps = [WorkoutStep(kind=RUN, duration_sec=100 * 60, pace_min="6:20", pace_max="6:40")]

    out = insert_fuel_cues(steps, [35, 70])

    runs = [s for s in out if not isinstance(s, CueStep)]

    assert all(s.duration_sec and s.distance_m is None for s in runs)
    assert abs(sum(s.duration_sec for s in runs) + 2 * CUE_SECONDS - 6000) <= 5
    assert len(_cues(out)) == 2


def test_gel_that_would_fall_inside_the_intervals_is_dropped_not_forced():
    """Nunca mexe nos tiros: o gel dentro do grupo que repete é descartado."""

    steps = [
        WorkoutStep(kind=WARMUP, distance_m=2000, pace_min="6:30", pace_max="7:00"),
        WorkoutStep(
            kind=REPEAT, reps=10,
            steps=[
                WorkoutStep(kind=INTERVAL, distance_m=800, pace_min="5:00", pace_max="5:10"),
                WorkoutStep(kind=RECOVERY, distance_m=400),
            ],
        ),
        WorkoutStep(kind=COOLDOWN, distance_m=2000, pace_min="6:30", pace_max="7:00"),
    ]

    out = insert_fuel_cues(steps, [35, 70], session_pace=5.2)

    assert out[1] is steps[1]  # o grupo segue intacto
    assert _cues(out) == []  # nenhum dos 2 gels cai fora dos tiros neste desenho


def test_an_open_lap_step_is_left_alone():

    steps = [WorkoutStep(kind=RUN)]

    assert insert_fuel_cues(steps, [35]) == steps


def test_a_gel_close_to_the_step_start_becomes_the_start_of_the_step():

    # gel aos 2 min do passo de 45 min -> o aviso abre o passo (sem pedaço de 2 min)
    steps = [WorkoutStep(kind=RUN, distance_m=7000, pace_min="6:20", pace_max="6:40")]

    out = insert_fuel_cues(steps, [2])

    assert isinstance(out[0], CueStep)
    assert abs(_meters(out) - 7000) <= 45


def test_a_gel_close_to_the_step_end_becomes_the_end_of_the_step():

    steps = [WorkoutStep(kind=RUN, distance_m=7000, pace_min="6:20", pace_max="6:40")]

    out = insert_fuel_cues(steps, [44], session_pace=6.5)

    assert isinstance(out[-1], CueStep)
    assert abs(_meters(out) - 7000) <= 45


def test_labels_for_optional_and_for_no_gel():

    steps = [WorkoutStep(kind=RUN, distance_m=14000, pace_min="6:20", pace_max="6:45")]

    optional = insert_fuel_cues(steps, [45], optional=True)

    assert _cues(optional)[0].note == "GEL (opcional) - com água"

    no_gel = insert_fuel_cues(steps, [35, 70], no_gel=True)

    assert _cues(no_gel)[0].note == (
        "REPOR agora (1 de 2): bala de goma, banana ou isotônico"
    )


# ---- o treino montado pro Garmin ----------------------------------------------------


def _fuel(times=(35, 70), optional=False, no_gel=False):

    return {"times": list(times), "optional": optional, "no_gel": no_gel}


def _all_steps(workout):

    return workout.workoutSegments[0].workoutSteps


def test_the_cue_notes_have_no_emoji_the_watch_font_cannot_draw():

    out = insert_fuel_cues(_simulado_steps(), [35, 70], session_pace=5.625)

    for cue in _cues(out):

        assert cue.note.isascii() is False or "🍬" not in cue.note
        assert "🍬" not in cue.note


def test_distances_are_whole_meters():

    out = insert_fuel_cues(_simulado_steps(), [35, 70], session_pace=5.625)

    for step in out:

        if step.distance_m:

            assert step.distance_m == int(step.distance_m)


def test_the_garmin_workout_carries_the_note_on_the_cue_steps_only():

    workout = GarminWorkoutBuilder.build(_session(), "Ritmind · Simulado", fuel=_fuel())

    steps = _all_steps(workout)

    dumped = [s.model_dump() for s in steps]

    notes = [d.get("description") for d in dumped if d.get("description")]

    assert notes == [
        "GEL agora (1 de 2) - com água",
        "GEL agora (2 de 2) - com água",
    ]

    # stepOrder sequencial, sem buracos
    assert [d["stepOrder"] for d in dumped] == list(range(1, len(dumped) + 1))

    # o aviso é um passo de TEMPO curto
    cue = next(d for d in dumped if d.get("description"))

    assert cue["endCondition"]["conditionTypeKey"] == "time"
    assert cue["endConditionValue"] == float(CUE_SECONDS)

    # a duração estimada soma os avisos
    assert workout.estimatedDurationInSecs > 0


def test_without_fuel_the_workout_is_exactly_what_it_was():

    plain = GarminWorkoutBuilder.build(_session(), "x")

    steps = _all_steps(plain)

    assert len(steps) == 3
    assert all(s.model_dump().get("description") is None for s in steps)


# ---- o envio: queda automática e a descrição -----------------------------------------


def _flag(on: bool):

    settings = MagicMock()

    settings.garmin_fuel_cues_active_for.side_effect = lambda p: on and p == "renato2"

    return patch("app.core.config.get_settings", return_value=settings)


def _garmin(fail_first=False):

    garmin = MagicMock()

    calls = {"n": 0}

    def upload(workout):

        calls["n"] += 1

        if fail_first and calls["n"] == 1:

            raise RuntimeError("400 Bad Request: description")

        return {"workoutId": 111}

    garmin.upload_running_workout.side_effect = upload
    garmin.schedule_workout.return_value = {"workoutScheduleId": 999}

    return garmin, calls


def _uploaded(garmin, call=0):

    return garmin.upload_running_workout.call_args_list[call].args[0]


def test_canary_profile_gets_the_cues_in_the_pushed_workout():

    garmin, calls = _garmin()

    with _flag(True), patch(REPO, return_value={"settings": {}}):

        out = push_session("renato2", _session(), date(2026, 10, 25), garmin)

    assert out["ok"] is True and calls["n"] == 1

    notes = [
        s.model_dump().get("description") for s in _all_steps(_uploaded(garmin))
        if s.model_dump().get("description")
    ]

    assert len(notes) == 2


def test_other_profiles_and_flag_off_get_the_workout_without_cues():

    for profile, on in (("mauricio", True), ("renato2", False)):

        garmin, calls = _garmin()

        with _flag(on), patch(REPO, return_value={"settings": {}}):

            out = push_session(profile, _session(), date(2026, 10, 25), garmin)

        assert out["ok"] is True and calls["n"] == 1

        assert all(
            s.model_dump().get("description") is None
            for s in _all_steps(_uploaded(garmin))
        )


def test_if_garmin_refuses_the_cues_the_workout_goes_up_without_them():
    """O treino nunca deixa de chegar ao relógio por causa do enfeite."""

    garmin, calls = _garmin(fail_first=True)

    with _flag(True), patch(REPO, return_value={"settings": {}}):

        out = push_session("renato2", _session(), date(2026, 10, 25), garmin)

    assert out["ok"] is True
    assert calls["n"] == 2

    assert any(
        s.model_dump().get("description") for s in _all_steps(_uploaded(garmin, 0))
    )
    assert all(
        s.model_dump().get("description") is None for s in _all_steps(_uploaded(garmin, 1))
    )


def test_a_real_failure_without_cues_still_raises_as_before():

    garmin = MagicMock()

    garmin.upload_running_workout.side_effect = RuntimeError("401")

    with _flag(False), patch(REPO, return_value={"settings": {}}):

        try:

            push_session("renato2", _session(), date(2026, 10, 25), garmin)

            raised = False

        except RuntimeError:

            raised = True

    assert raised


def test_the_workout_description_carries_the_nutrition_lines_for_everyone():
    """Sem canário nenhum: a descrição do treino (visível no Garmin Connect) já traz a
    orientação de gel — mesmo texto do plano."""

    garmin, _ = _garmin()

    with _flag(False), patch(REPO, return_value={"settings": {}}):

        push_session("mauricio", _session(), date(2026, 10, 25), garmin)

    description = _uploaded(garmin).description

    assert "Nutrição: gel (~25 g de carboidrato) aos 35 e 70 min" in description
    assert "Objetivo: Ensaio da prova" in description


def test_short_sessions_get_neither_description_lines_nor_cues():

    short = _session(
        steps=[WorkoutStep(kind=RUN, distance_m=8000, pace_min="6:20", pace_max="6:50")],
        km=8.0, kind="Rodagem Leve",
    )

    garmin, _ = _garmin()

    with _flag(True), patch(REPO, return_value={"settings": {}}):

        push_session("renato2", short, date(2026, 10, 22), garmin)

    workout = _uploaded(garmin)

    assert "Nutrição" not in (workout.description or "")
    assert len(_all_steps(workout)) == 1


def test_diabetes_in_the_nutrition_settings_blocks_the_cues():

    garmin, _ = _garmin()

    with _flag(True), patch(REPO, return_value={"settings": {"restrictions": "diabetes"}}):

        push_session("renato2", _session(), date(2026, 10, 25), garmin)

    assert all(
        s.model_dump().get("description") is None for s in _all_steps(_uploaded(garmin))
    )


# ---- o canário --------------------------------------------------------------------


def test_the_canary_flag():

    off = Settings(telegram_bot_token="x", google_api_key="x")

    assert off.garmin_fuel_cues_active_for("renato2") is False

    everyone = Settings(
        telegram_bot_token="x", google_api_key="x", garmin_fuel_cues_enabled=True,
    )

    assert everyone.garmin_fuel_cues_active_for("qualquer") is True

    canary = Settings(
        telegram_bot_token="x", google_api_key="x", garmin_fuel_cues_enabled=True,
        garmin_fuel_cues_profiles="renato2, leonardo",
    )

    assert canary.garmin_fuel_cues_profile_list == ["renato2", "leonardo"]
    assert canary.garmin_fuel_cues_active_for("renato2") is True
    assert canary.garmin_fuel_cues_active_for("mauricio") is False
