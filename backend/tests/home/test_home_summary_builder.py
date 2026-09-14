from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.application.home.home_summary_builder import HomeSummaryBuilder

MOD = "app.application.home.home_summary_builder"

# uma terça-feira fixa (2026-09-15) pra o "hoje" ser determinístico
_TUE = datetime(2026, 9, 15, 8, 0, 0)
_SUN = datetime(2026, 9, 13, 8, 0, 0)  # domingo, antes do week_start do plano


def _session(day, wtype):
    return SimpleNamespace(
        day=day,
        workout_type=wtype,
        objective="obj",
        planned_distance_km=8.0,
        planned_duration_minutes=None,
        target_pace_min="5:00",
        target_pace_max="5:10",
        steps=[],
    )


def _build_with(plan=None, body=None, fitness_health=None, pred=None, book=None):

    profiles = SimpleNamespace(
        load=lambda p: SimpleNamespace(name="Renato Teste", goal="10k")
    )

    with (
        patch(f"{MOD}.now_local", return_value=_TUE),
        patch(f"{MOD}.RunnerProfileRepository", lambda: profiles),
        patch(f"{MOD}.WeeklyPlanRepository", lambda: SimpleNamespace(load=lambda p: plan)),
        patch(f"{MOD}.GarminHealthRepository", lambda: SimpleNamespace(latest=lambda p: fitness_health)),
        patch(f"{MOD}.RacePredictionRepository", lambda: SimpleNamespace(load=lambda p: pred)),
        patch(f"{MOD}.ShoeRepository", lambda: SimpleNamespace(load=lambda p: book)),
    ):
        return HomeSummaryBuilder.build("tester")


def test_week_has_seven_days_and_marks_today():

    out = _build_with(plan=None)

    assert len(out["week"]) == 7
    today = [d for d in out["week"] if d["is_today"]]
    assert len(today) == 1
    assert today[0]["day_pt"] == "Ter"  # 2026-09-15 é terça


def test_todays_session_is_picked_from_plan():

    plan = SimpleNamespace(sessions=[_session("Tuesday", "Fartlek")])

    out = _build_with(plan=plan)

    assert out["today"]["session"]["workout_type"] == "Fartlek"
    assert out["today"]["session"]["kind"] == "tiro"


def test_rest_day_when_no_session_today():

    plan = SimpleNamespace(sessions=[_session("Thursday", "Rodagem")])

    out = _build_with(plan=plan)

    assert out["today"]["session"] is None
    # a quinta aparece na semana
    thu = [d for d in out["week"] if d["day_pt"] == "Qui"][0]
    assert thu["workout_type"] == "Rodagem"


def test_blocks_are_none_when_sources_empty():

    out = _build_with(plan=None, fitness_health=None, pred=None, book=None)

    assert out["body"] is None
    assert out["fitness"] is None
    assert out["shoe"] is None


def test_today_shows_next_workout_when_plan_is_future_week():
    """No domingo, com o plano já apontando pra semana que vem (week_start), o
    card destaca o PRÓXIMO treino, não um treino no dia errado."""

    plan = SimpleNamespace(
        week_start="2026-09-14",
        sessions=[_session("Tuesday", "Fartlek")],
    )
    profiles = SimpleNamespace(load=lambda p: SimpleNamespace(name="R", goal="x"))

    with (
        patch(f"{MOD}.now_local", return_value=_SUN),
        patch(f"{MOD}.RunnerProfileRepository", lambda: profiles),
        patch(f"{MOD}.WeeklyPlanRepository", lambda: SimpleNamespace(load=lambda p: plan)),
        patch(f"{MOD}.GarminHealthRepository", lambda: SimpleNamespace(latest=lambda p: None)),
        patch(f"{MOD}.RacePredictionRepository", lambda: SimpleNamespace(load=lambda p: None)),
        patch(f"{MOD}.ShoeRepository", lambda: SimpleNamespace(load=lambda p: None)),
    ):
        out = HomeSummaryBuilder.build("tester")

    assert out["today"]["label"] == "Próximo treino"
    assert out["today"]["day_en"] == "Tuesday"
    assert out["today"]["session"]["workout_type"] == "Fartlek"
    # o cabeçalho continua sendo o dia real de hoje (domingo)
    assert out["today"]["weekday_pt"] == "Dom"


def test_failing_block_does_not_break_home():
    """Se uma fonte estoura, aquele bloco vira None — a home nunca quebra."""

    def _boom(p):
        raise RuntimeError("garmin fora do ar")

    with (
        patch(f"{MOD}.now_local", return_value=_TUE),
        patch(f"{MOD}.RunnerProfileRepository", lambda: SimpleNamespace(load=lambda p: SimpleNamespace(name="R", goal="x"))),
        patch(f"{MOD}.WeeklyPlanRepository", lambda: SimpleNamespace(load=lambda p: None)),
        patch(f"{MOD}.GarminHealthRepository", lambda: SimpleNamespace(latest=_boom)),
        patch(f"{MOD}.RacePredictionRepository", lambda: SimpleNamespace(load=lambda p: None)),
        patch(f"{MOD}.ShoeRepository", lambda: SimpleNamespace(load=_boom)),
    ):
        out = HomeSummaryBuilder.build("tester")

    assert out["body"] is None
    assert out["shoe"] is None
    assert out["athlete"]["name"] == "R"
