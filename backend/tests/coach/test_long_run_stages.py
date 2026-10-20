"""O longão pode ter ETAPAS de ritmos diferentes (Renato, 19/10): início leve, trecho
moderado e um bloco longo no ritmo de prova fechando a distância — ex.: 2 km no pace
x, 5 km no pace y, 10 km no ritmo de prova = 17 km. O formato de passos já aceita; o
cardápio agora diz ao coach que essa forma existe."""

from app.application.coach.planning.workout_menu import ONE_OFF_MENU, WORKOUT_MENU
from app.application.garmin.garmin_workout_builder import GarminWorkoutBuilder
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.workout_step import RUN, parse_steps

STAGES = [
    {"kind": "run", "distance_km": 2, "pace_min": "6:30", "pace_max": "6:50"},
    {"kind": "run", "distance_km": 5, "pace_min": "6:00", "pace_max": "6:15"},
    {"kind": "run", "distance_km": 10, "pace_min": "5:30", "pace_max": "5:40"},
]


def test_the_menu_tells_the_coach_a_long_run_can_have_stages_of_different_pace():

    for menu in (WORKOUT_MENU, ONE_OFF_MENU):

        flat = " ".join(menu.split())  # o cardápio quebra linha no meio das frases

        assert "ETAPAS de ritmos diferentes" in flat
        assert "bloco longo no ritmo de prova" in flat
        assert "cada etapa é UM passo com o próprio pace" in flat


def test_the_variations_are_repertoire_for_every_type_not_a_rule():
    """Renato: não é regra — o coach tem a sabedoria; e vale pra TODOS os tipos."""

    for menu in (WORKOUT_MENU, ONE_OFF_MENU):

        flat = " ".join(menu.split())

        assert "Isto vale pra TODOS os tipos, não só o longão" in flat
        assert "Não é regra nem receita: é repertório" in flat
        assert "A sabedoria é sua, de treinador" in flat
        assert "o leve continua leve de verdade" in flat
        # nada prescritivo sobre o longão em etapas (sem "toda semana", sem fatia fixa)
        assert "não repete toda semana" not in flat


def test_the_menu_stays_free_of_braces_because_it_goes_into_a_format_string():

    assert "{" not in WORKOUT_MENU and "}" not in WORKOUT_MENU


def test_a_three_stage_long_run_is_parsed_as_three_steps_with_their_own_pace():

    steps = parse_steps(STAGES)

    assert [s.kind for s in steps] == [RUN, RUN, RUN]
    assert [s.distance_m for s in steps] == [2000, 5000, 10000]
    assert [s.pace_min for s in steps] == ["6:30", "6:00", "5:30"]
    assert sum(s.distance_m for s in steps) == 17000


def test_the_watch_workout_keeps_every_stage_as_a_step():
    """Cada etapa vira um passo guiado no relógio (apita na troca de ritmo)."""

    session = PlannedSession(
        day="Sunday", workout_type="Longão em etapas", objective="",
        planned_distance_km=17.0, planned_duration_minutes=None,
        target_pace_min="5:30", target_pace_max="6:50", steps=parse_steps(STAGES),
    )

    built = GarminWorkoutBuilder.build(session, "Longão em etapas")

    assert len(built.workoutSegments[0].workoutSteps) == 3
