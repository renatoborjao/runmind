"""AS DECISÕES DO COACH E A RECONSTRUÇÃO DAS CONVERSAS (nº 97). O log de decisões do cérebro (uma
entrada por mensagem: o que o atleta escreveu, o que o coach decidiu) estava guardado e ninguém o lia;
e é ele que ainda tem a fala do atleta de agosto a meados de setembro, que nenhum backup guardou.
Renato (01/11): "guarde todas as conversas dos atletas e faça com que o coach sempre tenha visibilidade"."""

from datetime import date

from app.application.history import coach_decisions
from app.application.history.coach_decisions import actions_of, render
from app.application.history.conversation_rebuild import known_keys, reconstruct

TODAY = date(2026, 11, 1)


def _entry(ts, incoming, say="", actions=None, action=None, on_pending=None):

    entry = {"ts": ts, "incoming": incoming, "say": say, "on_pending": on_pending}

    if actions is not None:

        entry["actions"] = actions

    if action is not None:

        entry["action"] = action

    return entry


def _act(kind, day=None, change=None):

    return {"type": kind, "scope": "single_session", "target_day": day, "content_change": change}


# ------------------------------------------------------------------ as decisões


def test_both_log_formats_give_the_actions_and_the_non_training_ones_are_left_out():

    assert [a["type"] for a in actions_of({"actions": [_act("move", "Sunday"), _act("shoe")]})] == ["move"]
    assert [a["type"] for a in actions_of({"action": _act("skip", "Friday")})] == ["skip"]
    assert actions_of({"action": None}) == [] and actions_of({"actions": [_act("watch")]}) == []


def test_the_block_counts_what_he_asks_and_what_the_coach_did_with_the_pattern_of_days():

    entries = [
        _entry("2026-10-16T08:00:00-03:00", "vamos cancelar o treino de hoje, muita chuva", action=_act("skip", "Friday")),
        _entry("2026-10-22T08:00:00-03:00", "cancele o treino de amanhã, sem ânimo", action=_act("skip", "Friday")),
        _entry("2026-10-27T08:00:00-03:00", "cancele o de hoje, muito frio", action=_act("skip", "Tuesday")),
        _entry("2026-09-02T08:00:00-03:00", "troca o longão para domingo", action=_act("move", "Sunday"), on_pending="refine"),
        _entry("2026-09-03T08:00:00-03:00", "e a rodagem fica quarta", action=_act("move", "Wednesday"), on_pending="reject"),
    ]

    text = render(entries, TODAY)

    assert text.startswith("SUAS DECISÕES COM ELE")
    assert "5 mensagens tratadas desde 02/09/26" in text
    assert "3 treino pulado a pedido" in text and "2 troca de dia" in text
    assert "Dias que ele mais pula: sexta (2x), terça (1x)" in text
    assert "Dia para onde ele mais passa o treino: domingo (1x), quarta (1x)" in text
    assert "1x pediu ajuste na proposta" in text and "1x recusou" in text
    assert '27/10 ele disse "cancele o de hoje, muito frio" → treino pulado a pedido (terça)' in text
    assert "CONHECIMENTO, não regra" in text and "Um pedido isolado" in text


def test_a_bare_yes_and_the_plan_pasted_back_are_not_listed_as_requests():

    entries = [
        _entry("2026-10-02T08:00:00-03:00", "o longo vou fazer domingo", action=_act("move", "Sunday")),
        _entry("2026-10-02T08:01:00-03:00", "Sim", action=_act("move", "Sunday")),
        _entry("2026-10-25T08:00:00-03:00", "🏃 Ritmind — Plano da semana, Bom domingo!", action=_act("adjust", "Saturday")),
    ]

    text = render(entries, TODAY)

    assert 'ele disse "o longo vou fazer domingo"' in text
    assert 'ele disse "Sim"' not in text and "Plano da semana" not in text
    assert "2 troca de dia" in text            # a conta do histórico segue inteira


def test_nothing_to_say_without_training_decisions():

    assert render([], TODAY) == ""
    assert render([_entry("2026-10-02T08:00:00-03:00", "qual tênis?", action=_act("shoe"))], TODAY) == ""


def test_unknown_action_types_still_show_with_their_own_name():

    text = render([_entry("2026-10-02T08:00:00-03:00", "troca de assessoria", action=_act("coach_switch"))], TODAY)

    assert "troca de treinador" in text


# ------------------------------------------------------------------ a reconstrução


def test_the_athletes_words_come_back_from_the_log_in_the_conversation_format():

    log = [
        _entry("2026-08-26T16:48:00-03:00", "Não vou conseguir seguir com minha assessora, preciso que você crie meus treinos",
               say="Fechado, Mauricio! Vou montar seus treinos a partir de agora."),
        _entry("2026-08-26T16:50:00-03:00", "Consegue já criar um treino pra amanhã?"),
    ]

    turns = reconstruct(log, known_turns=[])

    assert [(t["role"], t["text"][:30]) for t in turns] == [
        ("user", "Não vou conseguir seguir com m"),
        ("assistant", "Fechado, Mauricio! Vou montar "),
        ("user", "Consegue já criar um treino pr"),
    ]
    assert all(t["reconstructed"] for t in turns)
    assert turns[0]["timestamp"] == "2026-08-26T19:48:00+00:00"          # -03:00 virou UTC
    assert turns[1]["timestamp"] == "2026-08-26T19:48:01+00:00"


def test_what_the_conversation_already_has_is_not_repeated_even_across_the_utc_day_line():

    log = [_entry("2026-09-20T23:30:00-03:00", "Um ponto importante: eu jogo futebol toda terça às 21h")]

    # na conversa o mesmo instante está em UTC, já no dia seguinte
    known = [{"role": "user", "text": "Um ponto importante: eu jogo futebol toda terça às 21h e gostaria de",
              "timestamp": "2026-09-21T02:30:00+00:00"}]

    assert reconstruct(log, known) == []


def test_an_audio_is_recognised_by_its_transcription_even_when_the_app_shows_another_label():
    """Leonardo: a conversa guarda o rótulo de exibição e o log, a transcrição que o coach leu — a
    mesma fala. Sem isto ela seria duplicada."""

    known = [{"role": "user", "text": "Hoje eu tive que fazer meu treino na esteira", "display_text": "🎙️ áudio",
              "timestamp": "2026-10-09T21:43:00+00:00"}]

    assert ("2026-10-09", "hoje eu tive que fazer meu treino na esteira") in {
        (d.isoformat(), k) for d, k in known_keys(known)
    }

    log = [_entry("2026-10-09T18:43:00-03:00", "Hoje eu tive que fazer meu treino na esteira")]

    assert reconstruct(log, known) == []


def test_running_it_again_after_it_was_saved_adds_nothing():

    log = [_entry("2026-08-10T18:42:10-03:00", "preciso trocar meu treino de amanhã para quarta")]

    first = reconstruct(log, known_turns=[])

    assert len(first) == 1

    assert reconstruct(log, known_turns=first) == []


def test_empty_messages_and_broken_timestamps_are_skipped():

    log = [_entry("2026-08-10T18:42:10-03:00", "   "), _entry("não é data", "mensagem com data torta")]

    assert reconstruct(log, known_turns=[]) == []
    assert coach_decisions.render([_entry("não é data", "x", action=_act("move", "Sunday"))], TODAY) == ""
