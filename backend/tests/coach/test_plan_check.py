"""Base da semana + conferente do plano (puro, sem dado real): números do atleta × o plano."""

from datetime import date

from app.application.coach.planning import plan_check
from app.application.coach.planning.plan_check import HIGH, WATCH, CheckFacts
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan

WEEK = date(2026, 11, 23)


def _facts(**changes) -> CheckFacts:
    """O Leonardo de 16/11: limiar 5:49, VO2 5:21, leve a partir de 6:32, meta 10 km em 1h,
    entregou 22,7 km, maior corrida 10,5 km, prova em 4 semanas."""

    base = dict(
        threshold=5 + 49 / 60, vo2=5 + 21 / 60, easy_fast=6 + 32 / 60, race_goal=6.0,
        goal_km=10.0, goal_seconds=3600, weeks_to_race=4, delivering=True,
        last_done_km=22.7, last_planned_km=22.5, longest_30d_km=10.5,
    )

    base.update(changes)

    return CheckFacts(**base)


def _session(day, workout_type, km, structure=""):

    return PlannedSession(
        day=day, workout_type=workout_type, objective="", planned_distance_km=km,
        planned_duration_minutes=None, target_pace_min=None, target_pace_max=None,
        structure=structure,
    )


def _plan(*sessions, volume=None, route_note=None, is_deload=False):

    return TrainingPlan(
        athlete_name="L", objective="10k", phase="BUILD",
        weekly_volume=volume if volume is not None else sum(s.planned_distance_km for s in sessions),
        running_days=[s.day for s in sessions], week_start=WEEK, sessions=list(sessions),
        route_note=route_note, is_deload=is_deload,
    )


LIMIAR_LENTO = "Série Principal: 3 repetições de 1,5 km em ritmo de Limiar (6:10 a 6:20/km)."
LIMIAR_CERTO = "Série Principal: 5 repetições de 1 km em ritmo de Limiar (5:50 a 6:00/km)."


def _good_week(threshold=LIMIAR_CERTO):

    return _plan(
        _session("monday", "Rodagem Leve", 6.0, "Rodagem: 6 km leve (6:32 a 7:11/km)"),
        _session("friday", "Limiar", 8.0, threshold),
        _session("sunday", "Longão", 11.0, "Corrida contínua: 11 km (6:32 a 7:11/km)"),
    )


def _codes(issues):

    return {(i.code, i.level) for i in issues}


def test_a_coherent_week_has_nothing_to_fix():

    assert plan_check.check(_good_week(), _facts()) == []


def test_the_leonardo_threshold_slower_than_the_goal_is_high_with_the_numbers():

    issues = plan_check.check(_good_week(LIMIAR_LENTO), _facts())

    assert _codes(issues) == {("limiar_lento", HIGH)}
    assert "mais lento que o ritmo da meta (6:00)" in issues[0].text
    assert "21 s/km mais lento que o limiar de hoje dele (5:49)" in issues[0].text
    assert plan_check.needs_revision(issues)


def test_a_slow_threshold_for_who_does_not_deliver_is_not_flagged_when_the_goal_is_faster():
    """Quem não entrega: a régua pode estar otimista — e com a meta mais rápida que o limiar dele,
    limiar mais lento que a meta é normal."""

    facts = _facts(delivering=False, race_goal=5.5, last_done_km=22.0)

    assert plan_check.check(_good_week(LIMIAR_LENTO), facts) == []


def test_who_delivered_and_got_less_volume_without_a_reason_is_frozen():

    week = _good_week()

    week.weekly_volume = 20.0

    issues = plan_check.check(week, _facts())

    assert ("congelado", HIGH) in _codes(issues)
    assert "faixa 23,6 km–" in next(i.text for i in issues if i.code == "congelado")


def test_a_written_reason_or_a_deload_lets_the_coach_hold():

    week = _good_week()

    week.weekly_volume, week.route_note = 20.0, "Voltou de gripe na quinta: 20 km pra reabsorver."

    assert plan_check.check(week, _facts()) == []

    week.route_note, week.is_deload = None, True

    assert plan_check.check(week, _facts()) == []


def test_climbing_without_delivering_is_high():

    facts = _facts(delivering=False, last_done_km=12.0, sustained_km=14.0, best_recent_km=15.0)

    issues = plan_check.check(_good_week(), facts)

    assert ("subiu_sem_entregar", HIGH) in _codes(issues)


def test_one_missed_week_does_not_pin_the_plan_to_it():
    """Fernanda/Hélio 16/11: uma semana de 7 km depois de semanas de 20-28. Voltar ao patamar dela
    não é erro — só passar da melhor semana recente +10% é."""

    facts = _facts(
        delivering=False, last_done_km=7.0, last_planned_km=31.0,
        sustained_km=20.0, best_recent_km=28.0, longest_30d_km=15.0,
    )

    assert plan_check.check(_good_week(), facts) == []

    text = plan_check.base_block(facts)

    assert "sustentou ~20 km (melhor 28 km)" in text and "doença, viagem" in text


def test_extra_load_beyond_the_plan_is_not_the_next_step():
    """Mauricio 16/11: 50 km feitos com 38 planejados — a semana parte de 38, não de 50."""

    facts = _facts(last_done_km=50.0, last_planned_km=38.0, longest_30d_km=15.0)

    text = plan_check.base_block(facts)

    assert "planejou 38 km, fez 50 km" in text and "39,9 km–41,8 km" in text

    week = _good_week()

    week.weekly_volume = 40.0

    assert plan_check.check(week, facts) == []


def test_a_long_run_more_than_ten_percent_above_the_last_thirty_days_is_high():

    issues = plan_check.check(_good_week(), _facts(longest_30d_km=9.0))

    assert ("salto_longao", HIGH) in _codes(issues)


def test_softer_points_are_only_watch_and_never_cost_a_revision():

    week = _plan(
        _session("monday", "Rodagem Leve", 6.0, "Rodagem: 6 km (5:40 a 6:00/km)"),
        _session("wednesday", "Velocidade / VO2", 7.0, "Série Principal: 6x 400m (5:45 a 5:55/km)"),
        _session("friday", "Ritmo de Prova", 7.0, "Série Principal: 3x 1,2 km (6:20 a 6:30/km)"),
        _session("sunday", "Longão", 11.0, "Corrida contínua: 11 km (6:32 a 7:11/km)"),
    )

    issues = plan_check.check(week, _facts())

    assert _codes(issues) == {
        ("leve_forte", WATCH), ("vo2_lento", WATCH), ("ritmo_prova_lento", WATCH),
    }
    assert not plan_check.needs_revision(issues)


def test_the_correction_carries_only_the_high_points_and_leaves_the_decision_to_the_coach():

    issues = plan_check.check(_good_week(LIMIAR_LENTO), _facts(longest_30d_km=9.0))

    text = plan_check.correction_text(issues)

    assert "O CONFERENTE" in text and "limiar" in text and "maior treino" in text
    assert "mantenha e escreva o motivo com números em route_note" in text


def test_the_base_block_gives_the_numbers_up_front():

    text = plan_check.base_block(_facts())

    assert text.startswith("BASE DA SEMANA")
    assert "limiar ~5:49" in text and "ritmo da meta 6:00" in text and "leve ≥ 6:32" in text
    assert "ENTREGOU a última semana (planejou 22,5 km, fez 22,7 km)" in text
    assert "Faixa desta semana: 23,6 km–" in text
    assert "até 11,6 km" in text


def test_the_goal_reading_compares_what_the_goal_asks_with_today_and_the_time_left():

    text = plan_check.goal_reading(_facts())

    assert "pede VDOT" in text and "capacidade de hoje é VDOT" in text
    assert "AGRESSIVA" in text or "alcança a meta" in text or "JÁ cabe" in text


def test_a_goal_already_within_reach_says_so():

    text = plan_check.goal_reading(_facts(goal_seconds=3 * 3600))

    assert "A meta JÁ cabe" in text


def test_without_numbers_the_checks_stay_quiet():

    assert plan_check.check(_good_week(LIMIAR_LENTO), CheckFacts()) == []
    assert plan_check.base_block(CheckFacts()) == ""
