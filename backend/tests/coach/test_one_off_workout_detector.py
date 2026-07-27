from datetime import date

from app.application.coach.conversation.one_off_workout_detector import (
    OneOffWorkoutDetector,
)

# 2026-07-27 é uma segunda-feira
MONDAY = date(2026, 7, 27)


def test_detects_build_request():

    assert OneOffWorkoutDetector.looks_like_request(
        "monta um treino pra domingo"
    )
    assert OneOffWorkoutDetector.looks_like_request(
        "que treino faço amanhã?"
    )
    assert OneOffWorkoutDetector.looks_like_request(
        "me passa um treino pra sábado"
    )


def test_ignores_non_build_mentions_of_treino():
    """'como foi meu treino' e 'joga o treino pra quarta' NÃO são pedidos
    de montar treino avulso."""

    assert not OneOffWorkoutDetector.looks_like_request(
        "como foi meu treino de ontem?"
    )
    assert not OneOffWorkoutDetector.looks_like_request(
        "joga o treino de hoje pra quarta"
    )


def test_resolve_relative_dates():

    assert OneOffWorkoutDetector.resolve_target_date(
        "monta um treino pra hoje", MONDAY
    ) == date(2026, 7, 27)

    assert OneOffWorkoutDetector.resolve_target_date(
        "monta um treino pra amanhã", MONDAY
    ) == date(2026, 7, 28)

    assert OneOffWorkoutDetector.resolve_target_date(
        "faz um treino depois de amanhã", MONDAY
    ) == date(2026, 7, 29)


def test_resolve_weekday_next_occurrence():
    """Segunda 27/07 + 'domingo' -> o domingo seguinte (02/08)."""

    assert OneOffWorkoutDetector.resolve_target_date(
        "monta um treino pra domingo", MONDAY
    ) == date(2026, 8, 2)


def test_resolve_same_weekday_is_today():
    """Pedir o dia da semana de HOJE resolve pra hoje, não pra semana que vem."""

    assert OneOffWorkoutDetector.resolve_target_date(
        "monta um treino pra segunda", MONDAY
    ) == date(2026, 7, 27)


def test_resolve_numeric_date():

    assert OneOffWorkoutDetector.resolve_target_date(
        "monta um treino pro dia 01/08", MONDAY
    ) == date(2026, 8, 1)

    assert OneOffWorkoutDetector.resolve_target_date(
        "monta um treino pro dia 1 de agosto", MONDAY
    ) == date(2026, 8, 1)


def test_resolve_none_when_no_date():

    assert OneOffWorkoutDetector.resolve_target_date(
        "monta um treino pra mim", MONDAY
    ) is None
