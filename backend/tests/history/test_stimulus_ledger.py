from datetime import date, datetime, timedelta, timezone

from app.application.history.stimulus_ledger import (
    EASY,
    FARTLEK,
    HILLS,
    LONG,
    RACE,
    RACE_PACE,
    STEADY,
    STRIDES,
    TAPER,
    THRESHOLD,
    VO2,
    StimulusLedger,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_activity

TODAY = date(2026, 9, 26)  # sábado


def test_classify_real_plan_names():
    """Nomes REAIS dos planos do renato2 caem na família certa."""

    cases = {
        "Velocidade": VO2,
        "Intervalado de VO2": VO2,
        "Intervalado de Cruzeiro": THRESHOLD,
        "Intervalado de Limiar": THRESHOLD,
        "Tempo Run": THRESHOLD,
        "Rodagem por Tempo": EASY,
        "Treino Livre por Tempo": EASY,
        "Rodagem Moderada": STEADY,
        "Longão Progressivo": LONG,
        "Longão Misto": LONG,
        "Fartlek": FARTLEK,
        "Ativação Pré-Prova": TAPER,
        "Prova-Âncora 10K": RACE,
        "Simulado 8 km": RACE_PACE,
        "Blocos no pace de prova": RACE_PACE,
        "Subida (tiros em rampa)": HILLS,
        "Rodagem com acelerações": STRIDES,
        "Regenerativo": EASY,
    }

    for name, family in cases.items():

        assert StimulusLedger.classify(name) == family, name


def _plan(week_start, sessions):
    return TrainingPlan(
        athlete_name="R", objective="10k", phase="BUILD", weekly_volume=28,
        running_days=[d for d, _ in sessions], week_start=week_start,
        sessions=[
            PlannedSession(d, t, "", 8.0, None, None, None) for d, t in sessions
        ],
    )


def _run(day: date, hr=140, act_id=1):
    return make_activity(
        id=act_id,
        start_date=datetime(day.year, day.month, day.day, 9, tzinfo=timezone.utc),
        distance=8000.0, moving_time=3000, average_heartrate=hr,
    )


# régua do Renato real: máx 188, repouso 66 → leve < 151, forte >= 164
MAX_HR, REST_HR = 188, 66


def test_done_missed_last_and_gaps_toward_goal():

    w1 = date(2026, 9, 14)  # seg
    w2 = date(2026, 9, 21)

    plans = [
        _plan(w1, [("Tuesday", "Intervalado de VO2"), ("Saturday", "Longão")]),
        _plan(w2, [("Tuesday", "Fartlek"), ("Friday", "Tempo Run"),
                   ("Saturday", "Longão Progressivo")]),
    ]

    runs = [
        _run(w1 + timedelta(days=1), 160, 1),   # VO2 feito
        _run(w1 + timedelta(days=5), 145, 2),   # longão feito
        _run(w2 + timedelta(days=1), 158, 3),   # fartlek feito
        # sexta (tempo run) FUROU
        _run(w2 + timedelta(days=5), 148, 4),   # longão feito
    ]

    stats = StimulusLedger.families(plans, runs, TODAY)

    assert stats[VO2].done == 1
    assert stats[THRESHOLD].done == 0 and stats[THRESHOLD].missed == 1
    assert stats[LONG].done == 2 and stats[LONG].last_done == TODAY

    goal = TrainingGoal(
        name="10k sub-50", distance_km=10.0, target_time="50:00",
        race_date=TODAY + timedelta(weeks=8),
    )

    text = StimulusLedger.render(plans, runs, goal, TODAY, MAX_HR, REST_HR)

    assert "limiar: fez 0, furou 1" in text
    assert "ESPECÍFICA" in text
    # meta 10k: limiar e ritmo de prova são lacunas
    assert "LACUNAS" in text
    assert "limiar (nenhum em 8 sem)" in text
    assert "ritmo de prova / simulado (nenhum em 8 sem)" in text
    # subida fica fora do plano da semana (só avulso, quando o atleta pede):
    # não é lacuna
    assert "subida / força" not in text.split("LACUNAS")[1]
    assert "Intensidade real" in text


def test_grey_zone_is_flagged_by_heart_rate_reserve():
    """Leve (144) conta como leve; 155 é zona cinzenta (70-80% da reserva);
    165 é forte. Mesma régua pra todo o histórico."""

    runs = [
        _run(TODAY - timedelta(days=2), 144, 1),
        _run(TODAY - timedelta(days=4), 155, 2),
        _run(TODAY - timedelta(days=6), 156, 3),
        _run(TODAY - timedelta(days=8), 165, 4),
    ]

    split = StimulusLedger.zone_split(runs, TODAY, MAX_HR, REST_HR)

    assert (split.easy_pct, split.moderate_pct, split.hard_pct) == (25, 50, 25)

    plans = [_plan(date(2026, 9, 21), [("Thursday", "Rodagem")])]

    text = StimulusLedger.render(plans, runs, None, TODAY, MAX_HR, REST_HR)

    assert "zona cinzenta" in text


def test_no_zone_reading_without_resting_hr():
    """Sem FC de repouso, não lê intensidade — melhor calar que ler errado."""

    runs = [_run(TODAY - timedelta(days=2), 155, 1)]

    assert StimulusLedger.zone_split(runs, TODAY, MAX_HR, None) is None


def test_no_plans_renders_nothing():

    assert StimulusLedger.render([], [], None, TODAY) == ""
