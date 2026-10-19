"""O CICLO com várias provas: os sinais determinísticos (fase de rede, balanço de
estímulos, zona de taper da descarga) seguem o PAPEL da prova — e ficam IDÊNTICOS
ao de antes sem calendário. Casos reais: renato2 (15 km preparatória + meia
principal) e mauricio (uma prova futura só)."""

from datetime import date

from app.application.coach.planning.race_cycle import (
    focus_goal,
    focus_race,
    taper_zone_weeks,
    waypoint_note,
)
from app.application.history.deload_analyzer import DeloadAnalyzer
from app.application.history.stimulus_ledger import StimulusLedger
from app.application.planner.engines.phase_engine import PhaseEngine
from app.domain.entities.body_reading import FALLING, STABLE, RecoveryTrend
from app.domain.entities.training_goal import TrainingGoal


def _race(name, when, km, priority=None, suggested=None, target=None):

    return {
        "id": name, "name": name, "date": when, "distance_km": km,
        "target_time": target, "priority": priority,
        "priority_suggested": suggested,
        "priority_effective": priority or suggested,
    }


RENATO = [
    _race("Villa-Lobos (15 km)", "2026-12-20", 15.0, suggested="B", target="1:15:00"),
    _race("Meia SP (21 km)", "2027-04-04", 21.0975, suggested="A", target="1:59:59"),
]

MAURICIO = [
    _race("10 km", "2026-09-19", 10.0),
    _race("15 km", "2026-12-20", 15.0, suggested="A", target="01:22:30"),
]

# a âncora do perfil do renato2 = a prova mais próxima (o 15 km)
ANCHOR = TrainingGoal(
    name="meia maratona abaixo de 2h", distance_km=15.0,
    target_time="1:15:00", race_date=date(2026, 12, 20),
)


# ---- prova-foco -------------------------------------------------------------


def test_focus_is_the_principal_race_not_the_nearest():

    focus = focus_race(RENATO, date(2026, 10, 17))

    assert focus["name"] == "Meia SP (21 km)"


def test_without_calendar_there_is_no_focus_and_the_anchor_is_kept():
    """Mauricio: uma prova à frente — tudo como antes."""

    today = date(2026, 10, 17)

    assert focus_race(MAURICIO, today) is None
    assert taper_zone_weeks(MAURICIO, today) is None
    assert waypoint_note(MAURICIO, today) == ""

    anchor = TrainingGoal(
        name="baixar pace", distance_km=15.0, target_time="01:22:30",
        race_date=date(2026, 12, 20),
    )

    assert focus_goal(MAURICIO, today, anchor) is anchor


def test_focus_goal_carries_the_main_race_distance_date_and_target():

    goal = focus_goal(RENATO, date(2026, 10, 17), ANCHOR)

    assert goal.race_date == date(2027, 4, 4)
    assert goal.distance_km == 21.0975
    assert goal.target_time == "1:59:59"
    assert goal.name == ANCHOR.name


def test_phase_follows_the_focus_race_not_the_preparatory_one():
    """3 semanas antes do 15 km: pela âncora seria PEAK (afiação); pela meia, que
    é o foco (17 semanas), o ciclo segue em BASE."""

    today = date(2026, 11, 29)

    assert PhaseEngine.execute(ANCHOR, today) == "PEAK"

    assert PhaseEngine.execute(focus_goal(RENATO, today, ANCHOR), today) == "BASE"


# ---- zona de taper pelo papel ------------------------------------------------


def test_taper_zone_follows_the_role_of_the_next_race():

    today = date(2026, 10, 17)

    # próxima = preparatória (B) → mini-polimento
    assert taper_zone_weeks(RENATO, today) == 1

    # próxima = principal → padrão da descarga (None)
    only_main = [
        _race("A", "2026-12-20", 15.0, priority="A"),
        _race("B", "2027-04-04", 21.0975, priority="B"),
    ]
    assert taper_zone_weeks(only_main, today) is None

    # próxima = de treino → nenhuma
    training = [
        _race("C", "2026-12-20", 10.0, priority="C"),
        _race("A", "2027-04-04", 21.0975, priority="A"),
    ]
    assert taper_zone_weeks(training, today) == -1


def _recovery():
    """Um corpo CANSADO (recuperação caindo) — o único que a descarga atende."""

    return RecoveryTrend(hrv_direction=FALLING, rhr_direction=STABLE, days_covered=7)


def test_deload_is_not_swallowed_by_a_preparatory_race_two_weeks_away():
    """2 semanas pro 15 km (B): o padrão (zona de 3) calaria a descarga; com o
    papel B a zona é 1 — o corpo cansado segue sendo atendido."""

    loads = [80, 90, 100]

    legacy = DeloadAnalyzer.assess(loads, _recovery(), acwr=1.2, weeks_to_race=2)

    assert legacy.due is False and "taper" in legacy.reason

    role_aware = DeloadAnalyzer.assess(
        loads, _recovery(), acwr=1.2, weeks_to_race=2, taper_zone_weeks=1
    )

    assert role_aware.due is True


def test_deload_still_yields_to_the_mini_taper_in_the_last_week():

    d = DeloadAnalyzer.assess(
        [80, 90, 100], _recovery(), acwr=1.2, weeks_to_race=1, taper_zone_weeks=1
    )

    assert d.due is False and "taper" in d.reason


def test_training_race_never_silences_the_deload():

    d = DeloadAnalyzer.assess(
        [80, 90, 100], _recovery(), acwr=1.2, weeks_to_race=0, taper_zone_weeks=-1
    )

    assert d.due is True


def test_deload_default_is_unchanged_without_the_new_argument():

    assert DeloadAnalyzer.assess(
        [80, 90, 100], _recovery(), acwr=1.2, weeks_to_race=3
    ).due is False


# ---- balanço de estímulos: fase pela prova-foco ------------------------------


def test_ledger_phase_follows_the_focus_and_flags_the_waypoint():
    """7 semanas do 15 km: a régua é a meia (BASE) e o 15 km aparece como marco."""

    today = date(2026, 11, 1)

    goal, waypoint = StimulusLedger._cycle_view(ANCHOR, RENATO, today)

    assert goal.race_date == date(2027, 4, 4)

    text = StimulusLedger._gaps({}, goal, today, waypoint)

    assert "(BASE)" in text
    assert "prova de 21.1 km em 1:59:59 em 04/04/2027" in text
    assert "marco no caminho: 15 km em 20/12 (preparatória" in text
    assert "mini-polimento só na última semana" in text


def test_ledger_is_identical_without_a_calendar():

    today = date(2026, 11, 1)

    goal, waypoint = StimulusLedger._cycle_view(ANCHOR, MAURICIO, today)

    assert goal is ANCHOR and waypoint == ""

    assert StimulusLedger._gaps({}, goal, today, waypoint) == StimulusLedger._gaps(
        {}, ANCHOR, today
    )


def test_waypoint_is_silent_when_the_preparatory_race_is_far():
    """9 semanas até o 15 km: ainda não é assunto."""

    assert waypoint_note(RENATO, date(2026, 10, 17)) == ""
