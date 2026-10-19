"""O coach respeita o que o atleta diz de si e não repete o mesmo alerta. Caso real —
Renato, 17-18/10: depois de "me senti inteiro", "tô pronto pra carga" e "não tem mais
infecção", o chat repetiu a mesma cautela (14 km a 5:56 com FC 160) três vezes, e o
resumo de domingo mandou ele "segurar a ansiedade" (ele nunca disse que estava
ansioso). Validado com o modelo real em 19/10 (cenário 2: o atual repetiu o alerta em
3 de 3 amostras; o novo, em 2 de 3 — evidência fina, por isso o registro do alerta
também fica atrás de testes)."""

import json
from datetime import date
from unittest.mock import patch

from app.application.coach.conversation.coach_brain import (
    PROMPT_TEMPLATE,
    BrainDecision,
    CoachBrain,
)
from app.application.coach.writer.coach_persona import COACH_VOICE
from app.infrastructure.persistence.coach_attention_log import CoachAttentionLog
from tests.coach.test_coach_brain_executor import _run


def _parse(payload: dict):

    return CoachBrain._parse(json.dumps(payload))


# ---- B: a voz ----------------------------------------------------------------


def test_the_voice_treats_the_athletes_report_as_data_and_forbids_invented_states():

    assert "O QUE ELE DIZ DE SI É DADO" in COACH_VOICE
    assert "aceite" in COACH_VOICE
    assert "só volte ao assunto com dado NOVO" in COACH_VOICE
    # fala do treino, não de um estado interno que ele não contou
    assert "nunca de um estado interno que ele não contou" in COACH_VOICE
    assert "segure o ritmo na faixa X" in COACH_VOICE


def test_the_voice_keeps_its_older_rules():
    """A regra nova soma, não substitui: honestidade calibrada e puxar a orelha."""

    assert "HONESTIDADE CALIBRADA" in COACH_VOICE
    assert "PUXAR A ORELHA" in COACH_VOICE
    assert "ORIENTA, NÃO MANDA" in COACH_VOICE
    assert "PRECISÃO NA COBRANÇA" in COACH_VOICE


def test_the_brain_prompt_says_not_to_redo_an_alert_from_the_last_turns():

    assert "nem um alerta que VOCÊ mesmo já fez nos ÚLTIMOS TURNOS DA CONVERSA" in PROMPT_TEMPLATE
    assert "reconheça a decisão dele" in PROMPT_TEMPLATE


# ---- A: o alerta do chat vira memória ------------------------------------------


def test_the_brain_schema_asks_for_the_alert_it_made():

    assert '"cobranca"' in PROMPT_TEMPLATE
    assert "NÃO são cobrança: null" in PROMPT_TEMPLATE


def test_parse_reads_the_charge():

    d = _parse({"say": "Segura o ritmo.", "cobranca": "Alertei sobre a FC acima do teto."})

    assert d.cobranca == "Alertei sobre a FC acima do teto."


def test_parse_ignores_empty_null_and_oversized_charges():

    assert _parse({"say": "oi"}).cobranca is None
    assert _parse({"say": "oi", "cobranca": None}).cobranca is None
    assert _parse({"say": "oi", "cobranca": "  "}).cobranca is None
    assert _parse({"say": "oi", "cobranca": "null"}).cobranca is None
    assert _parse({"say": "oi", "cobranca": "None"}).cobranca is None

    long = _parse({"say": "oi", "cobranca": "x" * 500}).cobranca

    assert len(long) == 240


def test_a_charge_made_in_the_chat_is_recorded_for_the_next_message():

    decision = BrainDecision(
        say="Segura o ritmo no limiar.",
        cobranca="Alertei que o longão de sábado saiu com FC 160, acima do teto.",
    )

    with (
        patch(
            "app.infrastructure.persistence.coach_attention_log.CoachAttentionLog.record"
        ) as record,
        patch("app.core.clock.today_local", return_value=date(2026, 10, 19)),
    ):

        reply, _ = _run(decision)

    assert reply == "Segura o ritmo no limiar."

    record.assert_called_once_with(
        "renato", date(2026, 10, 19),
        "Alertei que o longão de sábado saiu com FC 160, acima do teto.", "chat",
    )


def test_no_charge_no_record():

    with patch(
        "app.infrastructure.persistence.coach_attention_log.CoachAttentionLog.record"
    ) as record:

        _run(BrainDecision(say="Bora! 👊"))

    record.assert_not_called()


def test_a_failure_to_record_never_breaks_the_reply():

    decision = BrainDecision(say="Segura o ritmo.", cobranca="Alertei sobre a FC.")

    with patch(
        "app.infrastructure.persistence.coach_attention_log.CoachAttentionLog.record",
        side_effect=OSError("disco cheio"),
    ):

        reply, _ = _run(decision)

    assert reply == "Segura o ritmo."


def test_chat_charges_show_up_labelled_in_the_next_prompt(tmp_path, monkeypatch):

    monkeypatch.setattr(
        "app.infrastructure.persistence.coach_attention_log._STORAGE", tmp_path,
    )

    CoachAttentionLog.record(
        "renato", date(2026, 10, 19), "Alertei sobre a FC do longão.", "chat",
    )

    rendered = CoachAttentionLog.render("renato", date(2026, 10, 20))

    assert "COBRANÇAS QUE VOCÊ JÁ FEZ" in rendered
    assert "19/10 (conversa): Alertei sobre a FC do longão." in rendered
    assert "NÃO repita a mesma bronca" in rendered
