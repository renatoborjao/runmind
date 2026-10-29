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


# --- ele ENTREGA o plano? (nº 86) ----------------------------------------------------------------


def _lw(week: int, planned: float, done: float, in_progress: bool = False):

    return week_ledger.LedgerWeek(
        week_start=date(2026, 9, 21 + 7 * week) if week < 2 else date(2026, 10, 5 + 7 * (week - 2)),
        phase="BUILD", objective="", deload=False, planned_km=planned, planned_sessions=3,
        planned_long_km=0.0, planned_key=[], done_km=done, done_runs=2 if done else 0,
        done_long_km=done / 2, fulfilled=1, missed=[], pending=[], extras=0,
        in_progress=in_progress, prev_done_km=0.0, quality_done_km=0.0,
    )


def _joao():
    """João (29/10): 5 semanas fechadas fazendo 5 a 14 km contra 10 a 19 km prescritos."""

    return [
        _lw(0, 10.0, 5.0), _lw(1, 14.5, 5.0), _lw(2, 17.1, 10.1),
        _lw(3, 17.1, 5.0), _lw(4, 19.3, 13.7), _lw(5, 12.4, 0.0, in_progress=True),
    ]


def test_an_athlete_who_closes_half_of_what_is_prescribed_does_not_deliver_the_plan():

    found = week_ledger.low_delivery(_joao())

    assert found is not None and round(found.ratio, 2) == 0.5
    assert found.done == [5.0, 5.0, 10.1, 5.0, 13.7] and round(found.median_done, 1) == 5.0
    assert found.median_runs == 2 and found.median_sessions == 3

    text = render(_joao())

    # a semana em andamento (12,4 prescritos, 0 até agora) não conta como furo
    assert "ENTREGA DO PLANO: nas últimas 5 semanas fechadas ele fez, na mediana, 50%" in text
    assert "fez 5, 5, 10,1, 5, 13,7 km contra 10, 14,5, 17,1, 17,1, 19,3 km prescritos" in text
    assert "correu ~2 dia(s) por semana contra 3 sessões prescritas" in text
    assert "ensine" not in text and "NÃO é descarga" not in text     # a diretriz é só do plano


def test_the_plan_voice_is_told_to_anchor_on_what_he_closes_and_not_to_call_it_a_deload():

    text = render(_joao(), directive=True)

    assert "REGRA DO RECUO (dada pelo dono do app)" in text and "DOIS motivos" in text
    assert "perto do que ele fecha (~5 km, no máximo uns +20%, ~6 km)" in text
    assert "os DIAS são os que ele cumpre (~2 por semana)" in text
    assert "nunca \"em linha com a rota\" se não estiver" in text
    assert "NÃO é descarga" in text and "doença, viagem ou lesão" in text


def test_an_athlete_who_delivers_or_overdelivers_has_no_delivery_warning():

    steady = [_lw(0, 13.1, 22.1), _lw(1, 7.5, 8.0), _lw(2, 22.1, 22.1), _lw(3, 23.5, 21.0)]

    assert week_ledger.delivery(steady).ratio >= 1.0
    assert week_ledger.low_delivery(steady) is None
    assert "ENTREGA DO PLANO" not in render(steady, directive=True)


def test_one_stopped_week_does_not_make_an_athlete_a_non_deliverer():
    """Hélio (29/10): duas semanas paradas por gripe e depois 33%, 36% e 39% ACIMA do prescrito."""

    helio = [
        _lw(0, 25.5, 0.0), _lw(1, 19.0, 0.0), _lw(2, 14.0, 18.7), _lw(3, 19.5, 26.5),
        _lw(4, 20.0, 27.8),
    ]

    assert week_ledger.low_delivery(helio) is None


def test_too_few_closed_weeks_say_nothing_about_delivery():

    assert week_ledger.delivery([_lw(0, 10.0, 3.0), _lw(1, 12.0, 4.0)]) is None
    running = [_lw(0, 10.0, 3.0), _lw(1, 12.0, 4.0), _lw(2, 9.0, 2.0, True)]

    assert week_ledger.delivery(running) is None
    assert week_ledger.delivery([]) is None
