"""A VISÃO DE TUDO (nº 95). O coach lia janelas (6-8 semanas, 200 mensagens, 26 leituras do corpo) e
do atleta antes disso só sabia pelo que a memória guardou; um mês raso depois de uma pausa médica
virou "risco alto" (Renato 01/11) porque a pausa não aparecia na mesma tela que a semana fraca.
Renato: "o coach precisa ter visão de tudo; o histórico é super importante — provas, tempos, paces".
É DADO + conhecimento, nunca regra."""

from datetime import date, datetime, timedelta

from app.application.history.athlete_timeline import build, render
from app.domain.entities.memory_entry import MemoryEntry
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_activity

TODAY = date(2026, 11, 1)           # domingo
WEEK = date(2026, 10, 26)           # a semana de hoje começa na segunda 26/10


def _run(day: date, km: float, pace_min: float = 6.5, act_id: int = 0, **over):

    seconds = km * pace_min * 60

    return make_activity(
        id=act_id or int(day.toordinal() * 10 + km),
        start_date=datetime(day.year, day.month, day.day, 9),
        distance=km * 1000, moving_time=int(seconds), average_speed=1000 / (pace_min * 60), **over,
    )


def _plan(week_start: date, km: float, deload=False):

    session = PlannedSession(
        day="Tuesday", workout_type="Rodagem", objective="", planned_distance_km=km,
        planned_duration_minutes=None, target_pace_min=None, target_pace_max=None,
    )

    return TrainingPlan(
        athlete_name="A", objective="meia", phase="BASE", weekly_volume=km, is_deload=deload,
        running_days=["Tuesday"], week_start=week_start, sessions=[session],
    )


def _memory(category, content, created, expires=None, status="active"):

    return MemoryEntry(
        id=content[:6], category=category, content=content, source="conversation",
        created_at=f"{created}T10:00:00-03:00", status=status, expires_at=expires,
    )


def _timeline(activities, **over):

    args = dict(
        activities=activities, plans=[], plan_versions=[], memory=[], checkins=[], body_readings=[],
        health=[], results=[], today=TODAY,
    )

    args.update(over)

    return build(**args)


def test_the_whole_curve_exists_week_by_week_even_the_weeks_he_did_not_run():

    runs = [_run(date(2026, 9, 1), 10.0), _run(date(2026, 9, 3), 8.0), _run(date(2026, 10, 13), 12.0)]

    timeline = _timeline(runs)

    assert timeline.first == date(2026, 9, 1)
    assert [w.start for w in timeline.weeks][0] == date(2026, 8, 31)
    assert timeline.weeks[-1].start == WEEK
    assert len(timeline.weeks) == 9

    first = timeline.weeks[0]

    assert first.km == 18.0 and first.runs == 2 and first.longest == 10.0

    stopped = timeline.weeks[3]

    assert stopped.km == 0 and stopped.runs == 0

    assert timeline.total_runs == 3 and timeline.best_week == (date(2026, 8, 31), 18.0)
    assert timeline.longest_run == (date(2026, 10, 13), 12.0)


def test_a_walk_marked_as_a_run_is_not_a_run():

    walk = _run(date(2026, 3, 2), 2.0, pace_min=15.0)

    timeline = _timeline([walk, _run(date(2026, 10, 13), 8.0)])

    assert timeline.first == date(2026, 10, 13) and timeline.total_runs == 1
    assert _timeline([walk]) is None
    assert render(None) == ""


def test_the_coachs_plan_sits_next_to_what_he_did_with_the_redone_versions():

    runs = [_run(date(2026, 10, 27), 15.0)]

    plans = [_plan(WEEK, 20.7, deload=True)]

    versions = [{"archived_at": "x", "reason": "r", "record": {"week_start": "2026-10-26"}}]

    text = render(_timeline(runs, plans=plans, plan_versions=versions))

    assert "- 26/10: 15 km · 1x, maior 15 · pace 6:30 · prescrito 21 (descarga), refeito 1x" in text


def test_the_specific_reason_comes_before_the_long_general_one():
    """Renato: na semana parada (pausa médica) as notas eram só 'dificuldade pra dormir', que dura
    meses; a pausa, que explica o zero, ficava de fora."""

    runs = [_run(date(2026, 9, 15), 10.0), _run(date(2026, 10, 12), 8.0)]

    memory = [
        _memory("vida", "Tem dificuldade para conseguir dormir cedo", "2026-09-04", "2026-11-30"),
        _memory("disponibilidade", "Sem treinar de 29/09 a 05/10, orientação médica", "2026-09-29", "2026-10-05"),
    ]

    text = render(_timeline(runs, memory=memory))

    line = next(line for line in text.splitlines() if line.startswith("- 28/09"))

    assert "Sem treinar de 29/09 a 05/10" in line
    assert line.index("Sem treinar") < line.index("dificuldade")


def test_expired_and_archived_memory_still_explains_the_past():

    runs = [_run(date(2026, 9, 15), 10.0), _run(date(2026, 10, 12), 8.0)]

    gripe = _memory("vida", "Teve gripe durante a semana de afastamento", "2026-10-05", "2026-10-12", status="archived")

    text = render(_timeline(runs, memory=[gripe]))

    assert "Teve gripe durante a semana de afastamento" in text
    assert "O QUE EXPLICA AS FASES" in text

    # preferência de tênis não explica fase nenhuma
    shoes = _memory("preferencia", "Usa o tênis Vomero", "2026-10-05")

    assert "Vomero" not in render(_timeline(runs, memory=[shoes]))


def test_the_same_fact_recorded_twice_is_listed_once():

    runs = [_run(date(2026, 9, 15), 10.0)]

    twice = [
        _memory("disponibilidade", "Dias de corrida a partir de 18/10: segunda, sexta e domingo", "2026-10-18"),
        _memory("disponibilidade", "Dias de corrida a partir de 18/10: segunda, sexta e domingo", "2026-10-18"),
    ]

    listed = [
        line for line in render(_timeline(runs, memory=twice)).splitlines()
        if line.startswith("- 18/10 (disponibilidade)")
    ]

    assert len(listed) == 1


def test_body_alerts_and_sleep_come_from_the_live_and_the_archived_readings():

    from types import SimpleNamespace

    runs = [_run(date(2026, 10, 13), 8.0)]

    body = [
        {"at": "2026-10-21T08:00:00-03:00", "body_state": "STRAINED"},         # arquivada
        {"at": "2026-10-22T08:00:00-03:00", "body_state": "BALANCED"},
    ]

    health = [SimpleNamespace(date="2026-10-27", sleep_hours=6.0), SimpleNamespace(date="2026-10-28", sleep_hours=5.0)]

    text = render(_timeline(runs, body_readings=body, health=health))

    assert "corpo: sobrecarregado" in text
    assert "sono 5,5h" in text


def test_every_race_with_time_and_pace_the_flagged_ones_and_the_ones_ahead():

    runs = [
        _run(date(2026, 8, 23), 10.0, pace_min=5.43),
        _run(date(2026, 6, 14), 5.0, pace_min=6.0, raw={"workout_type": 1}, name="Corrida de rua"),
        _run(date(2026, 10, 13), 8.0),
    ]

    results = [{
        "date": "2026-08-23", "distance_km": 10.03, "race_label": "10 km", "time": "54:18",
        "target_time": "00:55:00", "pace": "5:25", "beat": True,
    }]

    upcoming = [
        {"date": "2026-04-04", "name": "Meia de SP", "target_time": "1:59:59", "priority": "A"},
        {"date": "2025-01-01", "name": "Já passou"},
    ]

    records = {
        "pace_by_band": {"8-12": 5.42, "3-5": 6.37},
        "pace_by_band_dates": {"8-12": "2026-08-23", "3-5": "2026-08-18"},
    }

    # o dia de hoje do teste está antes de 04/04/2027
    text = render(_timeline(runs, results=results, upcoming=upcoming, records=records))

    assert "23/08/26 10 km: 54:18 (5:25/km, meta 00:55:00 ✔ bateu)" in text
    assert "14/06/26 Corrida de rua (5.0 km): 30:00 (6:00/km)" in text
    done = next(line for line in text.splitlines() if line.startswith("PROVAS FEITAS"))

    assert done.index("14/06/26") < done.index("23/08/26")                  # cronológico
    assert "Melhor pace médio por faixa de distância: 3-5 km: 6:22 (18/08/26) · 8-12 km: 5:25 (23/08/26)" in text
    assert "Meia de SP, meta 1:59:59, prioridade A" not in text           # 04/04/2026 já passou em relação a hoje
    assert "Já passou" not in text


def test_races_ahead_are_listed_with_their_goal():

    runs = [_run(date(2026, 10, 13), 8.0)]

    ahead = [{"date": "2027-04-04", "name": "Meia de SP", "target_time": "1:59:59", "priority": "A"}]

    assert "PROVAS À FRENTE: 04/04/27 Meia de SP, meta 1:59:59, prioridade A." in render(_timeline(runs, upcoming=ahead))
    assert "PROVAS FEITAS: nenhuma registrada." in render(_timeline(runs))


def test_old_weeks_collapse_into_months_and_the_recent_ones_keep_their_own_line():

    runs = []

    day = date(2026, 5, 4)

    while day < TODAY:

        runs.append(_run(day, 8.0))
        day += timedelta(days=7)

    text = render(_timeline(runs), plan_voice=True)

    lines = text.splitlines()

    month_lines = [l for l in lines if l.startswith("- mai/26") or l.startswith("- jun/26")]
    week_lines = [l for l in lines if l[:7].startswith("- ") and l[2:4].isdigit() and "km ·" in l]

    assert month_lines and "média 8,0 km/sem" in month_lines[0] and "pace médio 6:30" in month_lines[0]
    assert len(week_lines) == 12

    assert "CONHECIMENTO, não regra: este é o atleta INTEIRO" in text
    assert "CONHECIMENTO" not in render(_timeline(runs), plan_voice=False)
