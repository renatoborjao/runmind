"""MAPA ATÉ A PROVA (Renato, 20/10): o olhar pra frente que faltava. Calculado na hora, da
data da prova e das regras de periodização do coach; rotulado "previsto"; uma linha no
plano de domingo e uma linha do tempo na aba Treino; só pra quem tem prova com data.

Caso real: Maurício, 15 km em 20/12/2026 (domingo), plano da semana de 26/10 → 8 semanas:
construção 26/10–22/11, ritmo de prova 23/11–06/12, simulado 07–13/12, polimento 14–20/12."""

from datetime import date
from unittest.mock import patch

from app.application.coach.planning.race_map import (
    BASE,
    BUILD,
    MINI,
    RECOVERY,
    SIMULATED,
    SPECIFIC,
    TAPER,
    RaceMapBuilder,
    specific_weeks,
    taper_weeks,
)
from app.application.home.week_plan_builder import WeekPlanBuilder
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.domain.entities.training_plan import TrainingPlan

RACE = date(2026, 12, 20)  # domingo
WEEK = date(2026, 10, 26)  # segunda

CYCLE = "app.application.coach.planning.race_cycle.RaceCycle.races"


def _keys(race_map):

    return [(s.key, s.weeks) for s in race_map.segments]


# ---- o caso do Maurício ------------------------------------------------------------------------


def test_the_maurício_15k_has_eight_weeks_and_the_four_phases():

    m = RaceMapBuilder.build(RACE, 15.0, WEEK, name="15 km")

    assert m.weeks_left == 8
    assert _keys(m) == [(BUILD, 4), (SPECIFIC, 2), (SIMULATED, 1), (TAPER, 1)]

    spans = [(s.start, s.end) for s in m.segments]

    assert spans == [
        (date(2026, 10, 26), date(2026, 11, 22)),
        (date(2026, 11, 23), date(2026, 12, 6)),
        (date(2026, 12, 7), date(2026, 12, 13)),
        (date(2026, 12, 14), date(2026, 12, 20)),
    ]
    assert m.current.key == BUILD
    assert [s.current for s in m.segments] == [True, False, False, False]


def test_the_phase_lengths_follow_the_distance_like_the_coach_does():
    """10 km ~7–10 dias de polimento, meia ~10–14, maratona ~2–3 semanas."""

    assert taper_weeks(10.0) == 1 and specific_weeks(10.0) == 2
    assert taper_weeks(15.0) == 1
    assert taper_weeks(21.0975) == 2 and specific_weeks(21.0975) == 3
    assert taper_weeks(42.195) == 3 and specific_weeks(42.195) == 4
    assert taper_weeks(None) == 1  # sem distância: curto


def test_a_half_marathon_has_a_longer_taper_and_a_base_when_far():

    m = RaceMapBuilder.build(date(2027, 4, 4), 21.0975, date(2026, 10, 19), name="Maratona SP")

    # 24 semanas: 12 de base + construção 6 + ritmo de prova 3 + simulado 1 + polimento 2
    assert m.weeks_left == 24
    assert _keys(m) == [(BASE, 12), (BUILD, 6), (SPECIFIC, 3), (SIMULATED, 1), (TAPER, 2)]
    assert m.current.key == BASE


# ---- pouco tempo: sobra só o fim do ciclo ------------------------------------------------------


def test_with_little_time_left_only_the_end_of_the_cycle_remains():

    last = RaceMapBuilder.build(RACE, 15.0, date(2026, 12, 14))
    two = RaceMapBuilder.build(RACE, 15.0, date(2026, 12, 7))
    three = RaceMapBuilder.build(RACE, 15.0, date(2026, 11, 30))

    assert _keys(last) == [(TAPER, 1)]
    assert _keys(two) == [(SIMULATED, 1), (TAPER, 1)]
    assert _keys(three) == [(SPECIFIC, 1), (SIMULATED, 1), (TAPER, 1)]
    assert last.weeks_left == 1 and two.weeks_left == 2 and three.weeks_left == 3
    assert last.current.key == TAPER


# ---- bordas ------------------------------------------------------------------------------------


def test_a_race_that_passed_or_is_too_far_has_no_map():

    assert RaceMapBuilder.build(date(2026, 10, 18), 10.0, WEEK) is None
    assert RaceMapBuilder.build(date(2028, 1, 2), 10.0, WEEK) is None


def test_the_week_aligns_to_monday_even_when_given_a_midweek_day():

    wednesday = RaceMapBuilder.build(RACE, 15.0, date(2026, 10, 28))

    assert wednesday.weeks_left == 8
    assert wednesday.segments[0].start == date(2026, 10, 26)


def test_a_saturday_race_ends_the_taper_on_the_race_day():

    m = RaceMapBuilder.build(date(2026, 12, 19), 10.0, date(2026, 12, 14))

    assert m.segments[-1].key == TAPER
    assert m.segments[-1].end == date(2026, 12, 19)


# ---- a linha do plano de domingo ---------------------------------------------------------------


def test_the_sunday_line_is_one_line_with_the_arc_and_the_previsto_label():

    line = RaceMapBuilder.line(RaceMapBuilder.build(RACE, 15.0, WEEK, name="15 km"))

    assert "\n" not in line
    assert line == (
        "🗺️ Faltam 8 semanas pra 15 km (20/12): construção agora → ritmo de prova 23/11 "
        "→ simulado 07/12 → polimento 14/12. (previsto — se ajusta ao seu corpo)"
    )


def test_the_race_week_line_is_different():

    line = RaceMapBuilder.line(RaceMapBuilder.build(RACE, 15.0, date(2026, 12, 14)))

    assert line.startswith("🗺️ Semana da prova: 15 km em 20/12")
    assert "previsto" in line


def test_a_long_road_shows_only_the_next_step_and_the_end():

    line = RaceMapBuilder.line(
        RaceMapBuilder.build(date(2027, 4, 4), 21.0975, date(2026, 10, 19))
    )

    assert "pra meia maratona (04/04)" in line
    assert line.count("→") == 3
    assert "base agora" in line and "polimento" in line


def test_no_map_no_line():

    assert RaceMapBuilder.line(None) == ""
    assert RaceMapBuilder.payload(None) is None


# ---- o payload do app --------------------------------------------------------------------------


def test_the_app_payload_carries_phases_dates_markers_and_the_previsto_note():

    marker = {"label": "10 km", "date_iso": "2026-11-29", "role": "preparatória"}

    payload = RaceMapBuilder.payload(
        RaceMapBuilder.build(RACE, 15.0, WEEK, name="15 km", markers=[marker])
    )

    assert payload["target"] == "15 km"
    assert payload["race_date"] == "2026-12-20"
    assert payload["weeks_left"] == 8
    assert payload["current_key"] == BUILD
    assert [s["key"] for s in payload["segments"]] == [BUILD, SPECIFIC, SIMULATED, TAPER]
    assert payload["segments"][0] == {
        "key": BUILD, "label": "Construção", "start": "2026-10-26", "end": "2026-11-22",
        "weeks": 4, "current": True, "race_label": None,
    }
    assert payload["markers"] == [marker]
    assert payload["note"].startswith("Previsto")
    # sem números de volume: só fases e marcos
    assert "km_" not in str(payload) and "volume" not in str(payload)


# ---- da lista de provas do atleta --------------------------------------------------------------


def _race(day, km, role, name="prova"):

    return {
        "name": name, "date": day, "distance_km": km,
        "priority_effective": role, "priority": role,
    }


RENATO = [
    _race("2026-12-20", 15.0, "B", "15 km"),
    _race("2027-04-04", 21.0975, "A", "Maratona SP"),
]


def test_a_preparatory_race_is_a_stage_of_the_road_not_just_a_marker():
    """Renato2 (20/10): "eu também tenho como prova a do dia 20/12". A principal é a meia
    em abril, mas o 15 km de 20/12 está NO caminho: mini-polimento na semana dele e uma
    semana de recuperação depois — como o coach trata a preparatória."""

    with patch(CYCLE, return_value=RENATO):

        m = RaceMapBuilder.for_profile("renato2", WEEK)

    assert m.race_date == date(2027, 4, 4)
    assert m.race_name == "Maratona SP"
    assert m.markers == []
    assert m.waypoints == [{"label": "15 km", "date_iso": "2026-12-20", "weeks_left": 8}]

    assert [(s.key, s.weeks) for s in m.segments] == [
        (BASE, 7), (MINI, 1), (RECOVERY, 1), (BASE, 2), (BUILD, 6),
        (SPECIFIC, 3), (SIMULATED, 1), (TAPER, 2),
    ]

    mini = m.segments[1]

    assert mini.label == "15 km: mini-polimento e prova"
    assert mini.race_label == "15 km"
    assert (mini.start, mini.end) == (date(2026, 12, 14), date(2026, 12, 20))
    assert (m.segments[2].start, m.segments[2].end) == (date(2026, 12, 21), date(2026, 12, 27))
    # a meia continua com o polimento de 2 semanas até o dia da prova
    assert (m.segments[-1].start, m.segments[-1].end) == (date(2027, 3, 22), date(2027, 4, 4))
    assert m.current.key == BASE


def test_the_sunday_line_names_both_races_for_renato():

    with patch(CYCLE, return_value=RENATO):

        line = RaceMapBuilder.line(RaceMapBuilder.for_profile("renato2", WEEK))

    assert line == (
        "🗺️ Faltam 8 semanas pra 15 km (20/12) e 23 pra meia maratona (04/04): "
        "base agora → mini-polimento 14/12 → simulado 15/03 → polimento 22/03. "
        "(previsto — se ajusta ao seu corpo)"
    )


def test_a_preparatory_race_too_close_to_the_principal_is_only_a_marker():
    """Menos de ~3 semanas entre as provas: a de menor papel vira treino."""

    races = [
        _race("2026-12-06", 10.0, "B", "10 km"),
        _race("2026-12-20", 21.0975, "A", "Meia"),
    ]

    with patch(CYCLE, return_value=races):

        m = RaceMapBuilder.for_profile("p", WEEK)

    assert m.waypoints == []
    assert MINI not in [s.key for s in m.segments]
    assert m.markers == [
        {
            "label": "10 km", "date_iso": "2026-12-06", "role": "preparatória",
            "when": "before", "note": "perto da principal: entra como treino, sem polimento",
        }
    ]


def test_a_training_race_is_only_a_marker_and_a_later_race_is_told_as_after():

    races = [
        _race("2026-11-15", 10.0, "C", "10 km"),
        _race("2026-12-20", 15.0, "A", "15 km"),
        _race("2027-03-07", 21.0975, "B", "Meia"),
    ]

    with patch(CYCLE, return_value=races):

        m = RaceMapBuilder.for_profile("p", WEEK)

    assert m.waypoints == []
    assert MINI not in [s.key for s in m.segments]
    assert [(k["label"], k["when"], k["note"]) for k in m.markers] == [
        ("10 km", "before", "entra como treino, sem polimento"),
        ("meia maratona", "after", "depois da principal"),
    ]

    line = RaceMapBuilder.line(m)

    assert "Depois: meia maratona em 07/03." in line
    assert "Faltam 8 semanas pra 15 km (20/12):" in line


def test_a_waypoint_race_week_in_the_past_is_ignored_and_a_close_one_counts_the_weeks():

    one = RaceMapBuilder.build(
        date(2027, 4, 4), 21.0975, date(2026, 12, 14),
        waypoints=[{"date": date(2026, 12, 20), "label": "15 km"}],
    )

    assert one.segments[0].key == MINI and one.segments[0].current
    assert one.waypoints[0]["weeks_left"] == 1

    line = RaceMapBuilder.line(one)

    assert line.startswith("🗺️ Falta 1 semana pra 15 km (20/12) e 16 pra meia maratona (04/04):")

    passed = RaceMapBuilder.build(
        date(2027, 4, 4), 21.0975, date(2026, 12, 28),
        waypoints=[{"date": date(2026, 12, 20), "label": "15 km"}],
    )

    assert passed.waypoints == [] and MINI not in [s.key for s in passed.segments]


def test_the_principal_alone_keeps_the_old_line():
    """Sem preparatória no caminho a frase continua a de antes."""

    with patch(CYCLE, return_value=[RENATO[1]]):

        line = RaceMapBuilder.line(RaceMapBuilder.for_profile("p", WEEK))

    assert line.startswith("🗺️ Faltam 23 semanas pra meia maratona (04/04): base agora → ")
    assert "mini-polimento" not in line


def test_the_app_payload_carries_the_stage_race_and_the_marker_notes():

    with patch(CYCLE, return_value=RENATO):

        payload = RaceMapBuilder.payload(RaceMapBuilder.for_profile("renato2", WEEK))

    assert payload["target"] == "meia maratona"
    assert payload["markers"] == []

    stage = next(s for s in payload["segments"] if s["key"] == MINI)

    assert stage["race_label"] == "15 km"
    assert stage["label"] == "15 km: mini-polimento e prova"
    assert (stage["start"], stage["end"]) == ("2026-12-14", "2026-12-20")


def test_a_single_race_without_a_role_still_gets_a_map():

    with patch(CYCLE, return_value=[_race("2026-12-20", 10.0, None, "10 km")]):

        m = RaceMapBuilder.for_profile("leonardo", WEEK)

    assert m.race_date == RACE and m.markers == []
    assert m.weeks_left == 8


def test_without_principal_the_nearest_race_is_the_focus():

    races = [_race("2026-12-20", 10.0, "B"), _race("2027-02-14", 10.0, "C")]

    with patch(CYCLE, return_value=races):

        m = RaceMapBuilder.for_profile("p", WEEK)

    assert m.race_date == RACE


def test_no_dated_race_no_map_and_never_an_error():

    with patch(CYCLE, return_value=[]):

        assert RaceMapBuilder.for_profile("joao", WEEK) is None

    with patch(CYCLE, return_value=[_race("2026-08-23", 10.0, "A")]):

        assert RaceMapBuilder.for_profile("joao", WEEK) is None  # já passou

    with patch(CYCLE, side_effect=RuntimeError("disco")):

        assert RaceMapBuilder.for_profile("joao", WEEK) is None

    assert RaceMapBuilder.for_profile(None, WEEK) is None


# ---- onde o atleta lê --------------------------------------------------------------------------


def _plan(**kw) -> TrainingPlan:

    base = dict(
        athlete_name="Mauricio", objective="15k", phase="BUILD", weekly_volume=30.0,
        running_days=[], week_start=WEEK, sessions=[],
    )

    base.update(kw)

    return TrainingPlan(**base)


def test_the_plan_message_carries_the_map_line_right_after_the_phase():

    with patch(CYCLE, return_value=[_race("2026-12-20", 15.0, "A", "15 km")]):

        lines = WeeklyPlanMessageFormatter._phase_lines(_plan(), "mauricio")

    assert lines[0] == "📈 Fase: Construção"
    assert lines[1].startswith("🗺️ Faltam 8 semanas pra 15 km (20/12)")


def test_without_a_profile_or_a_race_the_message_is_unchanged():

    with patch(CYCLE, return_value=[]):

        with_profile = WeeklyPlanMessageFormatter._phase_lines(_plan(), "joao")

    without_profile = WeeklyPlanMessageFormatter._phase_lines(_plan())

    assert with_profile == without_profile == ["📈 Fase: Construção", ""]


def test_an_external_coach_plan_never_gets_the_map():

    with patch(CYCLE, return_value=[_race("2026-12-20", 15.0, "A")]):

        assert WeeklyPlanMessageFormatter._phase_lines(_plan(source="externo"), "x") == []


def test_a_failure_in_the_map_never_breaks_the_plan_message():

    with patch(
        "app.application.coach.planning.race_map.RaceMapBuilder.for_profile",
        side_effect=RuntimeError("boom"),
    ):

        lines = WeeklyPlanMessageFormatter._phase_lines(_plan(), "mauricio")

    assert lines == ["📈 Fase: Construção", ""]


def test_the_app_gets_the_map_only_in_the_current_week_of_a_runmind_plan():

    with patch(CYCLE, return_value=[_race("2026-12-20", 15.0, "A", "15 km")]):

        current = WeekPlanBuilder._race_map(_plan(), "mauricio", True)
        past = WeekPlanBuilder._race_map(_plan(), "mauricio", False)
        external = WeekPlanBuilder._race_map(_plan(source="externo"), "mauricio", True)

    assert current["weeks_left"] == 8 and current["current_key"] == BUILD
    assert past is None
    assert external is None


def test_a_failure_in_the_map_never_breaks_the_app_plan():

    with patch(CYCLE, side_effect=RuntimeError("disco")):

        assert WeekPlanBuilder._race_map(_plan(), "mauricio", True) is None
