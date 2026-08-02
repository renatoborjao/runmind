import pytest

from app.application.coach.conversation.proposal_reply_detector import (
    ProposalReply,
    ProposalReplyDetector,
)


@pytest.mark.parametrize(
    "text",
    [
        "sim",
        "pode ser",
        "manda ver",
        "beleza 👍",
        "fechou!",
        "isso, aplica",
        "perfeito, faz isso",
    ],
)
def test_confirmations(text):

    assert ProposalReplyDetector.detect(text) == ProposalReply.CONFIRM


@pytest.mark.parametrize(
    "text",
    [
        "não",
        "nao quero",
        "melhor não",
        "deixa quieto",
        "cancela",
    ],
)
def test_rejections(text):

    assert ProposalReplyDetector.detect(text) == ProposalReply.REJECT


@pytest.mark.parametrize(
    "text",
    [
        "prefiro quarta",
        "e o longão de sábado?",
        "por que essa troca?",
    ],
)
def test_unclear_is_not_forced(text):

    assert ProposalReplyDetector.detect(text) == ProposalReply.UNCLEAR


def test_reject_wins_when_message_mixes_both():

    # "nao pode" tem sinal de recusa E de aceite: recusa ganha (não aplica
    # nada sem um sim limpo)
    assert ProposalReplyDetector.detect("nao pode") == ProposalReply.REJECT


@pytest.mark.parametrize(
    "text",
    [
        "pode, mas prefiro quarta",
        "sim, porém no sábado",
        "isso, só que mais leve",
    ],
)
def test_qualified_yes_is_not_an_automatic_apply(text):

    # aceite com ressalva é contraproposta -> não aplica sozinho
    assert ProposalReplyDetector.detect(text) == ProposalReply.UNCLEAR


@pytest.mark.parametrize(
    "text",
    [
        # bug real (02/08): a preposição "para" casava como recusa (verbo
        # parar) e descartava a proposta. Ressalva de rumo não é "não".
        "digo para a partir de semana que vem",
        "para de segunda a sexta",
        "só os treinos de terça e quinta",
    ],
)
def test_para_preposition_is_not_a_rejection(text):

    assert ProposalReplyDetector.detect(text) != ProposalReply.REJECT


def test_cue_inside_a_word_does_not_trigger():

    # "sim" dentro de "assim"/"simples" NÃO pode virar um aceite — só
    # palavra inteira conta
    assert ProposalReplyDetector.detect("simples assim") == (
        ProposalReply.UNCLEAR
    )
