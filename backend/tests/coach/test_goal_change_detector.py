from app.application.coach.conversation.goal_change_detector import (
    GoalChangeDetector,
)


def test_detects_explicit_goal_change():

    assert GoalChangeDetector.looks_like_goal_change(
        "quero mudar minha meta pra sub-45"
    )


def test_detects_new_goal_stated_directly():

    assert GoalChangeDetector.looks_like_goal_change(
        "meu objetivo agora é só saúde"
    )


def test_question_about_the_race_is_not_a_change():
    """'qual a minha prova mesmo?' é pergunta, não pedido de troca."""

    assert not GoalChangeDetector.looks_like_goal_change(
        "qual a minha prova mesmo?"
    )


def test_no_goal_word_is_not_a_change():
    """'muda meu treino de terça' é sobre o PLANO, não a meta."""

    assert not GoalChangeDetector.looks_like_goal_change(
        "muda meu treino de terça pra quinta"
    )


def test_no_change_cue_is_not_a_change():

    assert not GoalChangeDetector.looks_like_goal_change(
        "gosto muito da minha meta atual"
    )
