from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.application.home.home_summary_builder import HomeSummaryBuilder

MOD = "app.application.home.home_summary_builder"

# uma terça-feira fixa (2026-09-15) pra o "hoje" ser determinístico
_TUE = datetime(2026, 9, 15, 8, 0, 0)
_SUN = datetime(2026, 9, 13, 8, 0, 0)  # domingo, antes do week_start do plano


def _health_repo(series):
    """Fake do GarminHealthRepository sobre uma lista de DailyHealth (ordenada
    por data), implementando o que a home usa: latest e latest_where."""

    series = series or []

    return SimpleNamespace(
        latest=lambda p: series[-1] if series else None,
        latest_where=lambda p, pred: next(
            (h for h in reversed(series) if pred(h)), None
        ),
    )


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


def _build_with(plan=None, health_series=None, fitness_health=None, pred=None, book=None):

    # compat: quem passa um único fitness_health vira uma série de um dia
    if health_series is None:
        health_series = [fitness_health] if fitness_health is not None else []

    profiles = SimpleNamespace(
        load=lambda p: SimpleNamespace(name="Renato Teste", goal="10k")
    )

    with (
        patch(f"{MOD}.now_local", return_value=_TUE),
        patch(f"{MOD}.RunnerProfileRepository", lambda: profiles),
        patch(f"{MOD}.WeeklyPlanRepository", lambda: SimpleNamespace(load=lambda p: plan)),
        patch(f"{MOD}.GarminHealthRepository", lambda: _health_repo(health_series)),
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
        week_start=date(2026, 9, 14),  # entidade real usa date
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
        patch(f"{MOD}.GarminHealthRepository", lambda: SimpleNamespace(latest=_boom, latest_where=lambda p, pred: _boom(p))),
        patch(f"{MOD}.RacePredictionRepository", lambda: SimpleNamespace(load=lambda p: None)),
        patch(f"{MOD}.ShoeRepository", lambda: SimpleNamespace(load=_boom)),
    ):
        out = HomeSummaryBuilder.build("tester")

    assert out["body"] is None
    assert out["shoe"] is None
    assert out["athlete"]["name"] == "R"


def test_body_uses_last_day_with_recovery_not_hollow_today():
    """Regressão (o bug do 'dormi e acordei sem'): o dia CORRENTE nasce oco — o
    relógio sincroniza stress/SpO2/bateria corrente antes do sono da noite. Esse
    dia não pode virar a leitura do corpo (herói em branco); a home mostra o
    último dia COM leitura da manhã (sono/HRV/prontidão/bateria ao acordar)."""

    from app.domain.entities.daily_health import DailyHealth

    ontem = DailyHealth(
        date="2026-09-14", sleep_hours=7.2, hrv_last_night=42,
        resting_hr=54, body_battery_at_wake=78, readiness_score=81, vo2max=52.0,
    )
    hoje_oco = DailyHealth(  # só o "agora": stress/SpO2/bateria corrente
        date="2026-09-15", stress_avg=30, spo2_avg=96,
        body_battery_most_recent=5,
    )

    out = _build_with(health_series=[ontem, hoje_oco])

    assert out["body"] is not None
    assert out["body"]["date"] == "2026-09-14"       # não o dia oco
    assert out["body"]["readiness_score"] == 81
    assert out["body"]["ring"]["value"] == 81
    # o VO₂máx também não some num dia sem medição
    assert out["fitness"]["vo2max"] == 52.0


def test_body_shows_today_once_morning_reading_lands():
    """Assim que HOJE captura a leitura da manhã, o herói passa a mostrar HOJE
    (a leitura same-day continua funcionando)."""

    from app.domain.entities.daily_health import DailyHealth

    ontem = DailyHealth(date="2026-09-14", sleep_hours=7.0, readiness_score=70)
    hoje = DailyHealth(date="2026-09-15", sleep_hours=8.1, readiness_score=90)

    out = _build_with(health_series=[ontem, hoje])

    assert out["body"]["date"] == "2026-09-15"
    assert out["body"]["readiness_score"] == 90
