"""LEMBRANÇA DA CONVERSA (nº 96). As mensagens que saíram da janela de 200 e tudo que o coach enviou
ficam no arquivo permanente; quando o atleta pergunta "o que a gente combinou em julho?" ou "lembra
do joelho?", o coach responde com o que foi DITO. Busca léxica, sem IA e sem custo."""

from datetime import date
from unittest.mock import patch

from app.application.history import conversation_recall
from app.application.history.conversation_recall import (
    Turn,
    date_window,
    for_message,
    render,
    search,
    tokens,
)

TODAY = date(2026, 11, 1)


def _turn(day: date, role: str, text: str) -> Turn:

    return Turn(day, role, text)


def _padding(count: int = conversation_recall.SKIP_RECENT) -> list[Turn]:
    """As últimas turnas: o chat já as carrega, então a busca as ignora."""

    return [_turn(date(2026, 10, 30), "atleta", f"mensagem recente {i}") for i in range(count)]


CORPUS = [
    _turn(date(2026, 7, 6), "atleta", "estou com uma dor no joelho direito quando desço escada"),
    _turn(date(2026, 7, 6), "coach", "Vamos poupar o joelho: troca o tiro por rodagem leve e me conta amanhã."),
    _turn(date(2026, 7, 20), "atleta", "meu objetivo é correr os 10 km abaixo de 50 minutos em agosto"),
    _turn(date(2026, 8, 3), "atleta", "comprei um tênis novo para os treinos longos"),
    _turn(date(2026, 8, 15), "coach (mensagem enviada)", "Análise do longão de 14 km: ritmo estável, joelho sem queixa."),
]


def test_words_without_content_are_dropped_and_accents_do_not_matter():

    assert tokens("Lembra do Joelho? Falei ontem, né") == {"joelho"}
    assert tokens("TÊNIS novo, preço da corrida") == {"tenis", "novo", "preco"}


def test_the_month_he_cites_becomes_a_window():

    assert date_window("o que a gente combinou em julho?", TODAY) == (date(2026, 7, 1), date(2026, 7, 31))
    assert date_window("e em dezembro?", TODAY) == (date(2025, 12, 1), date(2025, 12, 31))   # ainda não chegou
    assert date_window("no mês passado", TODAY) == (date(2026, 10, 1), date(2026, 10, 31))
    assert date_window("lembra do dia 15/08", TODAY) == (date(2026, 8, 12), date(2026, 8, 18))
    assert date_window("bora treinar", TODAY) is None


def test_a_real_match_brings_the_old_passage_with_the_answer_the_coach_gave():

    hits = search(CORPUS + _padding(), "lembra do que eu falei sobre o joelho direito?", TODAY)

    assert [h.turn.day for h in hits][0] == date(2026, 7, 6)

    athlete = next(h for h in hits if h.turn.role == "atleta")

    assert "dor no joelho direito" in athlete.turn.text
    assert "troca o tiro por rodagem leve" in athlete.reply


def test_the_sent_messages_of_the_coach_are_searched_too():

    hits = search(CORPUS + _padding(), "você analisou meu longão de 14 km, como foi?", TODAY)

    assert any(h.turn.role == "coach (mensagem enviada)" for h in hits)


def test_a_short_or_common_message_brings_nothing():

    for text in ("bora", "valeu coach", "como está o treino de hoje?", ""):

        assert search(CORPUS + _padding(), text, TODAY) == []


def test_one_shared_ordinary_word_is_not_enough_but_a_rare_one_is():

    corpus = CORPUS + [_turn(date(2026, 9, 1), "atleta", "treino muito legal hoje")] * 8

    assert search(corpus + _padding(), "tênis", TODAY) == []              # curta/comum demais (<6 letras raras)

    hits = search(corpus + _padding(), "e o joelho, melhorou?", TODAY)

    assert hits and "joelho" in hits[0].turn.text


def test_a_cited_period_limits_the_search_to_it():

    hits = search(CORPUS + _padding(), "o que a gente combinou em julho?", TODAY)

    assert hits and all(date(2026, 7, 1) <= h.turn.day <= date(2026, 7, 31) for h in hits)
    assert not any("tênis" in h.turn.text for h in hits)


def test_the_last_turns_are_never_repeated_because_the_chat_already_has_them():

    recent = _turn(date(2026, 10, 31), "atleta", "estou com dor no joelho esquerdo")

    old_filler = _turn(date(2026, 6, 1), "atleta", "treino de segunda ficou bom")

    # a turna recente está entre as últimas SKIP_RECENT: o chat já a carrega
    turns = [old_filler, recent] + _padding(conversation_recall.SKIP_RECENT - 1)

    assert search(turns, "dor no joelho", TODAY) == []

    # a mesma turna, já fora da janela recente, é achada
    turns = [recent, old_filler] + _padding()

    assert [h.turn.text for h in search(turns, "dor no joelho", TODAY)] == ["estou com dor no joelho esquerdo"]


def test_the_block_is_literal_dated_and_neutral():

    hits = search(CORPUS + _padding(), "lembra do que eu falei sobre o joelho direito?", TODAY)

    text = render(hits)

    assert text.startswith("LEMBRANÇAS DA CONVERSA")
    assert '- 06/07/26 (atleta): "estou com uma dor no joelho direito' in text
    assert "→ coach respondeu:" in text
    assert "CONHECIMENTO, não regra" in text and "Não force uma lembrança" in text

    assert render([]) == ""


def test_the_corpus_joins_live_archive_and_outbox_without_repeating(tmp_path):

    from app.infrastructure.persistence.coach_outbox_repository import CoachOutboxRepository
    from app.infrastructure.persistence.conversation_repository import ConversationRepository
    from app.infrastructure.persistence.permanent_archive import PermanentArchive

    conversations = ConversationRepository()
    conversations.storage = tmp_path / "conversations"
    conversations.storage.mkdir()

    outbox = CoachOutboxRepository()
    outbox.storage = tmp_path / "coach_outbox"
    outbox.storage.mkdir()

    old = {"role": "user", "text": "dor no joelho direito", "timestamp": "2026-07-06T10:00:00+00:00"}
    live = {"role": "assistant", "text": "vamos poupar o joelho", "timestamp": "2026-07-06T10:01:00+00:00"}

    (conversations.storage / "atleta.json").write_text(
        __import__("json").dumps([live]), encoding="utf-8",
    )

    PermanentArchive.append(conversations.storage, "conversations", "atleta", [old, live], "teste")
    PermanentArchive.append(
        outbox.storage, "coach_outbox", "atleta",
        [{"text": "Análise do longão", "timestamp": "2026-08-15T09:00:00+00:00"}], "teste",
    )

    with patch("app.infrastructure.persistence.conversation_repository.ConversationRepository", return_value=conversations), \
         patch("app.infrastructure.persistence.coach_outbox_repository.CoachOutboxRepository", return_value=outbox):

        turns = conversation_recall.load("atleta")

    assert [(t.day.isoformat(), t.role) for t in turns] == [
        ("2026-07-06", "atleta"), ("2026-07-06", "coach"), ("2026-08-15", "coach (mensagem enviada)"),
    ]


def test_for_message_is_empty_when_nothing_matches():

    with patch.object(conversation_recall, "load", return_value=CORPUS + _padding()):

        assert for_message("atleta", "bora", TODAY) == ""
        assert "joelho" in for_message("atleta", "lembra do joelho direito?", TODAY)


def test_the_chat_context_never_breaks_when_the_recall_fails():

    from app.application.coach.conversation.conversation_context_builder import (
        ConversationContextBuilder,
    )

    with patch.object(conversation_recall, "for_message", side_effect=RuntimeError("falhou")):

        assert ConversationContextBuilder._conversation_recall("atleta", "joelho", TODAY) == ""

    assert ConversationContextBuilder._conversation_recall("atleta", "   ", TODAY) == ""


def test_training_marks_survive_the_cleaning_and_plurals_become_singular():
    """'sub-50', '10 km' e '10k' eram apagados por serem curtos; 'joelhos' não casava com 'joelho'."""

    assert tokens("a meta de sub-50 nos 10 km, 10k e 21 k") == {"meta", "sub50", "10km", "21km"}
    assert tokens("dores nos joelhos") == {"dore", "joelho"} or "joelho" in tokens("dores nos joelhos")


def test_a_mark_alone_is_enough_to_match():

    corpus = [_turn(date(2026, 7, 20), "atleta", "quero fechar os 10 km em menos de 50 minutos")] + _padding()

    hits = search(corpus + _padding(0), "lembra dos 10 km que eu queria?", TODAY)

    assert hits and "10 km" in hits[0].turn.text


def test_when_i_started_points_to_the_first_days_of_the_story():

    first = date(2026, 7, 4)

    assert date_window("quando comecei, qual era o objetivo?", TODAY, first) == (first, date(2026, 8, 18))
    assert date_window("quando comecei, qual era o objetivo?", TODAY) is None

    turns = [
        _turn(first, "atleta", "meu objetivo é correr 10 km abaixo de 50 minutos até agosto"),
        _turn(date(2026, 10, 1), "atleta", "agora quero treinar para a meia maratona de abril"),
    ] + _padding()

    hits = search(turns, "qual era meu objetivo quando comecei?", TODAY)

    assert [h.turn.day for h in hits] == [first]


def test_automatic_messages_barely_count_when_only_a_period_is_cited():
    """'o que combinamos em julho?' trazia plano e leitura automáticos, não o que foi combinado."""

    automatic = [
        _turn(date(2026, 7, day), "coach (mensagem enviada)", "🏃 Bom dia! Hoje é dia de treino " * 8)
        for day in range(1, 10)
    ]

    talk = [
        _turn(date(2026, 7, 12), "atleta", "vou treinar terça, quinta e sábado, domingo é de descanso total"),
        _turn(date(2026, 7, 12), "coach", "Combinado: terça, quinta e sábado. Domingo descansa."),
    ]

    hits = search(automatic + talk + _padding(), "o que a gente combinou em julho?", TODAY)

    roles = [h.turn.role for h in hits]

    assert len(hits) == 5
    assert "atleta" in roles and "coach" in roles


def test_a_ready_made_plan_or_reading_is_not_what_was_agreed():

    from app.application.history.conversation_recall import _templated

    assert _templated("🏃 Seu próximo treino, Renato:\n\n🔹 quinta-feira (30/07) — Rodagem · 8.5 km")
    assert _templated("🩺 Leitura do corpo\n\n⚖️ Renato, seu corpo está absorvendo bem")
    assert not _templated("Combinado: terça, quinta e sábado. Domingo descansa.")

    plan_reply = _turn(date(2026, 7, 29), "coach", "🏃 Seu próximo treino, Renato:\n\n🔹 quinta (30/07) — Rodagem " * 3)
    agreed = _turn(date(2026, 7, 12), "coach", "Combinado: terça, quinta e sábado. Domingo descansa.")

    hits = search([plan_reply, agreed] * 4 + _padding(), "o que combinamos em julho?", TODAY, k=2)

    assert all("Combinado" in h.turn.text for h in hits)
