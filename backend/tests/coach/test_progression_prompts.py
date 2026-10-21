"""O coach VÊ a evolução e o pedido do atleta — e precisa AGIR (nº 76). Leonardo (21/10): com a
forma estagnada, 0% de esforço forte e ele dizendo que os treinos estavam leves, o coach deu o
menor passo semana após semana. As instruções que fecham isso nos três lugares onde o coach decide:
o plano, o chat e a calibração do leve."""

from app.application.coach.conversation.coach_brain import PROMPT_TEMPLATE as BRAIN_PROMPT
from app.application.coach.planning.coach_plan_engine import PROMPT_TEMPLATE as PLAN_PROMPT
from app.application.coach.writer.coach_persona import COACH_VOICE
from app.application.history.execution_log import HEADER


def test_the_plan_must_close_the_route_gap_and_answer_the_request_with_dose():

    assert "ROTA ATÉ A META e PEDIDO DO ATLETA" in PLAN_PROMPT
    assert "feche a DIFERENÇA nas" in PLAN_PROMPT
    assert "semana igual à anterior sem dizer por quê é" in PLAN_PROMPT
    assert "a resposta é DOSE" in PLAN_PROMPT
    # o leve segue definido pela FC: o pace do leve de verdade vence a faixa do modelo
    assert "use ESSA faixa e não a do modelo" in PLAN_PROMPT
    # a faixa do leve é a desta semana, não a copiada do plano anterior
    flat = " ".join(PLAN_PROMPT.split())

    assert 'a "fácil" das "Paces reais" DESTA semana' in flat
    assert "não copie a faixa do plano anterior" in flat


def test_the_chat_never_just_notes_that_he_wants_more():

    assert "PEDIDO DE MAIS CARGA" in BRAIN_PROMPT
    assert 'nunca só "anotei"' in BRAIN_PROMPT
    assert 'ação "replan"' in BRAIN_PROMPT

    # o prompt segue formatável (as chaves do JSON de exemplo são escapadas)
    BRAIN_PROMPT.format(
        runner_name="Leonardo", voice=COACH_VOICE, context_facts="", pending_block="",
        history_block="", cards="race", message="oi",
    )


def test_the_easy_pace_band_is_a_ceiling_unless_the_heart_rate_says_it_got_slow():

    assert "a faixa é TETO" in HEADER
    assert "SALVO se a FC dele ficou abaixo do teto aeróbico" in HEADER
    assert "a régua do leve é a FC" in HEADER
