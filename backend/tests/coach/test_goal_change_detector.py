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


def test_explicit_change_request_true_on_clear_intent():
    """'quero trocar meus objetivos' é pedido claro de troca — arma o
    estado mesmo sem dizer a meta ainda."""

    assert GoalChangeDetector.is_explicit_change_request(
        "quero trocar meus objetivos"
    )
    assert GoalChangeDetector.is_explicit_change_request(
        "preciso mudar minha meta"
    )


def test_explicit_change_request_false_on_weak_cue():
    """Falso positivo do portão barato ('prova' + 'agora') NÃO é pedido
    explícito de troca — não deve armar o estado nem perguntar à toa."""

    assert not GoalChangeDetector.is_explicit_change_request(
        "a prova que fiz agora foi ótima"
    )
    # sem palavra de meta, mesmo com verbo de troca, não é troca de objetivo
    assert not GoalChangeDetector.is_explicit_change_request(
        "quero trocar meu treino de terça"
    )
