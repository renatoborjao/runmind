from datetime import date

from app.application.coach.planning.body_conduct_engine import (
    BodyConductEngine,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan

WEEK = date(2026, 7, 6)  # segunda


def _session(day, wtype, km) -> PlannedSession:

    return PlannedSession(day, wtype, "", km, None, "5:00", "5:20")


def _plan(sessions) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato", objective="10k", phase="IA",
        weekly_volume=30.0, running_days=[s.day for s in sessions],
        week_start=WEEK, sessions=sessions,
    )


# ------------------- is_demanding (exigência) -------------------


def test_rodagem_por_tempo_nao_e_exigente():
    """O bug do Renato: 'Rodagem por Tempo' é rodagem LEVE medida por duração —
    o 'tempo' (de 'por tempo') não pode fazer virar treino puxado."""

    assert not BodyConductEngine.is_demanding(
        _session("Friday", "Rodagem por Tempo", 8.0)
    )


def test_regenerativo_e_trote_leve_nao_sao_exigentes():

    assert not BodyConductEngine.is_demanding(
        _session("Monday", "Corrida Regenerativa", 6.0)
    )
    assert not BodyConductEngine.is_demanding(
        _session("Monday", "Trote leve", 5.0)
    )


def test_rodagem_PUXADA_segue_exigente():
    """O Renato lembrou: existe rodagem puxada. O fix da colisão 'por tempo' NÃO
    pode chapar toda rodagem como leve — progressiva/forte/em ritmo é exigente."""

    assert BodyConductEngine.is_demanding(
        _session("Friday", "Rodagem Progressiva", 10.0)
    )
    assert BodyConductEngine.is_demanding(
        _session("Friday", "Rodagem em Ritmo Forte", 8.0)
    )
    # e uma rodagem progressiva medida POR TEMPO também segue exigente
    assert BodyConductEngine.is_demanding(
        _session("Friday", "Rodagem Progressiva por Tempo", 8.0)
    )


def test_treinos_de_qualidade_seguem_exigentes():
    """A correção do 'easy manda' não pode amortecer os treinos que SÃO puxados."""

    for wtype in (
        "Intervalado de Limiar", "Longão com Blocos de Ritmo",
        "Tiros de VO2", "Fartlek", "Progressivo",
    ):

        assert BodyConductEngine.is_demanding(_session("Wednesday", wtype, 8.0))


# ------------------- next_demanding_session -------------------


def _week_plan():

    return _plan([
        _session("Tuesday", "Velocidade", 9.0),
        _session("Thursday", "Rodagem", 8.0),
        _session("Saturday", "Longão", 14.0),
    ])


def test_finds_next_intense_session():

    # segunda: o próximo exigente é a Velocidade de terça
    s = BodyConductEngine.next_demanding_session(_week_plan(), WEEK, set())

    assert s.day == "Tuesday"


def test_skips_easy_and_finds_the_long_run():

    # quarta: terça passou; pula a Rodagem de quinta (leve) e acha o longão
    s = BodyConductEngine.next_demanding_session(
        _week_plan(), date(2026, 7, 8), set(),
    )

    assert s.day == "Saturday"


def test_done_days_are_skipped():

    # quarta, longão de sábado já feito adiantado: sobra só a Rodagem leve
    s = BodyConductEngine.next_demanding_session(
        _week_plan(), date(2026, 7, 8), {"Saturday"},
    )

    assert s is None


def test_falls_back_to_longest_run_when_none_labeled_demanding():

    plan = _plan([
        _session("Tuesday", "Rodagem", 8.0),
        _session("Saturday", "Rodagem longa", 12.0),
    ])

    # nenhuma rotulada intensa, mas 12km >= 10 conta como exigente
    s = BodyConductEngine.next_demanding_session(plan, WEEK, set())

    assert s.day == "Saturday"


def test_no_demanding_when_all_short_and_easy():

    plan = _plan([
        _session("Tuesday", "Rodagem", 6.0),
        _session("Thursday", "Rodagem", 7.0),
    ])

    assert BodyConductEngine.next_demanding_session(plan, WEEK, set()) is None


# ------------------- _parse -------------------


def _target():

    return _session("Saturday", "Longão", 14.0)


def test_parse_keep_has_no_operations():

    d = BodyConductEngine._parse(
        '{"action": "keep", "message": ""}', _week_plan(), _target(),
    )

    assert d.action == "keep"
    assert d.operations == []


def test_parse_ease_builds_light_session():

    d = BodyConductEngine._parse(
        '{"action": "ease", "ease_km": 8, "message": "Alivio amanhã?"}',
        _week_plan(), _target(),
    )

    assert d.action == "ease"
    op = d.operations[0]
    assert op["action"] == "replace"
    assert op["day"] == "Saturday"
    assert op["session"]["planned_distance_km"] == 8
    assert op["session"]["workout_type"] == "Rodagem leve"
    assert op["session"]["adjusted"] is True
    assert op["session"]["steps"] == []


def test_parse_ease_ignores_km_not_lighter_than_original():

    # ease_km 20 (>= 14 original) é rejeitado -> cai em ~60% (8.4 -> 8)
    d = BodyConductEngine._parse(
        '{"action": "ease", "ease_km": 20, "message": "x"}',
        _week_plan(), _target(),
    )

    assert d.operations[0]["session"]["planned_distance_km"] == 8


def test_parse_move_to_free_day():

    d = BodyConductEngine._parse(
        '{"action": "move", "target_day": "Sunday", "message": "movo?"}',
        _week_plan(), _target(),
    )

    assert d.action == "move"
    assert d.operations[0] == {"action": "drop", "day": "Saturday"}
    assert d.operations[1]["day"] == "Sunday"


def test_parse_move_to_occupied_day_is_rejected():

    # terça já tem treino -> mover pra lá apagaria; rejeita
    d = BodyConductEngine._parse(
        '{"action": "move", "target_day": "Tuesday", "message": "x"}',
        _week_plan(), _target(),
    )

    assert d is None


def test_parse_garbage_is_none():

    assert BodyConductEngine._parse("não é json", _week_plan(), _target()) is None
    assert BodyConductEngine._parse(
        '{"action": "ease", "message": ""}', _week_plan(), _target(),
    ) is None  # ease sem message
