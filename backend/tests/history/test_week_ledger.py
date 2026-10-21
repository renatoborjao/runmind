"""SEMANAS ANTERIORES — prescrito × feito (nº 80). O plano de domingo via o prescrito num lugar e o
feito em outro, e o coach saltou de 8 km pra 22 km (+175% sobre o que o atleta fez) porque cada
semana nascia do papel da anterior. O livro-razão põe os dois lado a lado, com o objetivo que o
próprio coach deu e a rota daquela semana: o que o atleta FEZ é o chão da semana nova."""

from datetime import UTC, date, datetime

from app.application.history import week_ledger
from app.application.history.week_ledger import build, render, run_km_by_week, typical
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_activity

W1 = date(2026, 10, 5)
W2 = date(2026, 10, 12)
W3 = date(2026, 10, 19)
REF = date(2026, 10, 26)      # a semana que o plano monta


def _session(day, workout_type, km):

    return PlannedSession(
        day=day, workout_type=workout_type, objective="", planned_distance_km=km,
        planned_duration_minutes=None, target_pace_min=None, target_pace_max=None,
    )


def _plan(week_start, volume, *sessions, objective="", deload=False, route=None, note=None,
          source="runmind"):

    return TrainingPlan(
        athlete_name="L", objective="10k", phase="BUILD", weekly_volume=volume,
        running_days=[s.day for s in sessions], week_start=week_start, sessions=list(sessions),
        weekly_objective=objective, is_deload=deload, route=route, route_note=note, source=source,
    )


def _run(day: date, km: float, act_id: int):

    return make_activity(
        id=act_id, distance=km * 1000, moving_time=int(km * 380),
        start_date=datetime(day.year, day.month, day.day, 9, tzinfo=UTC),
    )


def _leonardo_weeks():
    """05/10 papel 13 → fez 22 (4 corridas); 12/10 papel 7,5 → fez 8; 19/10 papel 22 → 1."""

    plans = [
        _plan(W1, 13.1, _session("Monday", "Rodagem Leve", 5.0),
              _session("Friday", "Ritmo de Prova", 8.0), objective="Introduzir o ritmo de prova"),
        _plan(W2, 7.5, _session("Sunday", "Limiar", 7.5), objective="Consolidar após o salto"),
        _plan(W3, 22.1, _session("Monday", "Rodagem Leve", 6.0),
              _session("Friday", "Velocidade / VO2", 7.1), _session("Sunday", "Longão", 9.0),
              objective="Retomar a frequência de 3 treinos"),
    ]

    runs = [
        _run(date(2026, 10, 5), 5.0, 1), _run(date(2026, 10, 6), 4.0, 2),
        _run(date(2026, 10, 9), 9.0, 3), _run(date(2026, 10, 11), 4.1, 4),
        _run(date(2026, 10, 18), 8.0, 5), _run(date(2026, 10, 19), 6.0, 6),
    ]

    return plans, runs


def test_each_week_pairs_what_was_prescribed_with_what_was_done():

    plans, runs = _leonardo_weeks()

    weeks = build(plans, runs, date(2026, 10, 21), REF)

    first, second, third = weeks

    assert (first.planned_km, first.done_km, first.done_runs) == (13.1, 22.1, 4)
    assert first.fulfilled == 2 and first.extras == 2 and not first.missed
    assert first.planned_key == ["Ritmo de Prova"]
    assert second.planned_km == 7.5 and round(second.done_km, 1) == 8.0
    # o papel de 12/10 caiu 66% sobre o que ele fez (22,1 km)
    assert round(second.prev_done_km, 1) == 22.1
    assert third.in_progress and third.fulfilled == 1


def test_a_week_still_in_progress_shows_what_is_missing_instead_of_counting_a_miss():

    plans, runs = _leonardo_weeks()

    third = build(plans, runs, date(2026, 10, 21), REF)[-1]

    assert third.pending == ["sex Velocidade / VO2 7.1 km", "dom Longão 9 km"] and not third.missed

    # no domingo à noite (o plano da semana nova sai agora), o que ficou por fazer é furo
    closed = build(plans, runs, date(2026, 10, 25), REF)[-1]

    assert not closed.in_progress and not closed.pending
    assert closed.missed == ["sex Velocidade / VO2 7.1 km", "dom Longão 9 km"]


def test_the_render_shows_the_jump_of_the_paper_over_what_he_did():

    plans, runs = _leonardo_weeks()

    text = render(build(plans, runs, date(2026, 10, 25), REF), directive=True)

    assert "prescreveu ~22,1 km em 3 sessões" in text and "fez 6 km em 1 corrida" in text
    # papel × feito da semana anterior: 22,1 → 7,5 e 8 → 22,1
    assert "O papel foi -66% sobre o que ele fez na semana anterior (22,1 km)" in text
    assert "O papel foi +176% sobre o que ele fez na semana anterior (8 km)" in text
    assert '"Retomar a frequência de 3 treinos"' in text
    assert "NÃO fez: sex Velocidade / VO2 7.1 km, dom Longão 9 km" in text


def test_a_week_in_progress_is_not_judged_by_percent():

    plans, runs = _leonardo_weeks()

    text = render(build(plans, runs, date(2026, 10, 21), REF))

    assert "(em andamento)" in text and "fez 6 km em 1 corrida até agora" in text
    assert "(-73%)" not in text


def test_what_he_sustains_ignores_the_week_in_progress_and_weeks_without_running():

    plans, runs = _leonardo_weeks()

    weeks = build(plans, runs, date(2026, 10, 21), REF)

    median_km, best, longest = typical(weeks)

    # só 05/10 (22,1) e 12/10 (8) são fechadas
    assert round(best, 1) == 22.1 and round(median_km, 2) == round((22.1 + 8.0) / 2, 2)
    assert longest == 9.0
    assert typical([]) is None


def test_the_plan_voice_gets_the_knowledge_and_the_others_only_the_facts():

    plans, runs = _leonardo_weeks()

    weeks = build(plans, runs, date(2026, 10, 25), REF)

    assert "o que ele não cumpriu não foi dose absorvida" in render(weeks, directive=True)
    assert "CONHECIMENTO" not in render(weeks)
    assert "O que ele SUSTENTA" in render(weeks)
    assert render([]) == ""


def test_the_route_the_plan_kept_and_the_motive_come_back_next_to_what_happened():

    route = {"weeks": [{"w": "2026-10-12", "ph": "construcao", "km": [11.9, 14.5], "vol": 13.2}]}

    plans = [_plan(W2, 7.5, _session("Sunday", "Limiar", 7.5), route=route,
                   note="Semana leve porque ele dormiu 2h na véspera")]

    week = build(plans, [_run(date(2026, 10, 18), 8.0, 1)], date(2026, 10, 25), REF)[0]

    text = render([week])

    assert week.route_km == (11.9, 14.5)
    assert "Rota previa 11,9–14,5 km" in text
    assert "Seu motivo: Semana leve porque ele dormiu 2h na véspera" in text


def test_only_our_plans_count_and_the_deload_flag_is_shown():

    plans = [
        _plan(W1, 10, _session("Monday", "Rodagem Leve", 5.0), source="externo"),
        _plan(W2, 6, _session("Sunday", "Rodagem Leve", 6.0), deload=True),
    ]

    weeks = build(plans, [], date(2026, 10, 25), REF)

    assert [w.week_start for w in weeks] == [W2]
    assert "descarga" in render(weeks) and "não correu" in render(weeks)


def test_the_km_by_week_only_counts_real_runs():

    by_week = run_km_by_week([_run(date(2026, 10, 5), 5.0, 1), _run(date(2026, 10, 6), 0.4, 2)])

    assert by_week == {W1: [5.0]}


def test_module_exposes_the_window():

    assert week_ledger.WINDOW_WEEKS == 6


# --- o plano guarda a rota e o motivo; o coach recebe as instruções ------------------------------


def test_the_plan_keeps_the_route_and_the_reason_when_saved_and_loaded():
    from app.infrastructure.persistence.weekly_plan_repository import WeeklyPlanRepository

    route = {
        "v": 1, "rolling": False,
        "weeks": [{"w": "2026-10-26", "ph": "construcao", "km": [11.9, 14.5]}],
    }

    plan = _plan(W3, 22.1, _session("Monday", "Rodagem Leve", 6.0), route=route, note="Semana leve")

    again = WeeklyPlanRepository._from_dict(WeeklyPlanRepository._to_dict(plan))

    assert again.route == route and again.route_note == "Semana leve"

    # plano antigo (sem os campos) segue carregando
    old = WeeklyPlanRepository._to_dict(plan)

    old.pop("route")
    old.pop("route_note")

    legacy = WeeklyPlanRepository._from_dict(old)

    assert legacy.route is None and legacy.route_note is None


def test_the_plan_prompt_asks_for_the_motive_outside_the_route_and_forbids_repeating_the_dose():
    from app.application.coach.planning.coach_plan_engine import PROMPT_TEMPLATE, CoachPlanEngine

    flat = " ".join(PROMPT_TEMPLATE.split())

    assert "SEMANAS ANTERIORES e ROTA SEMANA A SEMANA" in flat
    assert "A semana nasce do que ele FEZ, nunca do papel" in flat
    assert "±20% do dela SEM precisar justificar" in flat and '"route_note"' in flat
    assert "ESTAGNAR" in flat and "EVOLUÍREM juntos" in flat
    assert "a rota é guia, não trilho" in flat

    note = "Pausa de 5 dias por gripe"

    assert CoachPlanEngine._route_note({"route_note": note}) == note
    assert CoachPlanEngine._route_note({"route_note": None}) is None
    assert CoachPlanEngine._route_note({"route_note": "null"}) is None
    assert CoachPlanEngine._route_note({}) is None
