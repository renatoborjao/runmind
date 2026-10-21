"""ELE PEDE MAIS. Caso real (Leonardo): em 02/10 escreveu que as metas e os treinos estavam muito
leves, em 18/10 que "estava demorando muito pra chegar ao objetivo"; o relato ficou numa linha do
dossiê e a dose não mudou por 19 dias. O que o atleta diz de si é dado — pesado com o corpo e o
esforço percebido, nunca ignorado em silêncio."""

from datetime import date, datetime, timedelta

from app.application.history.athlete_asks_more import (
    Ask,
    asks_more_directive,
    asks_more_fact,
    dose_since,
    find,
    says_more,
)
from tests.coach.factories import make_activity

# as frases REAIS do Leonardo (resumidas só nas pontas)
_TOO_EASY = (
    "Obrigado, eu estou começando nesse mundo a corrida, mas não sei, eu venho achando as metas "
    "muito baixas para o meu ritmo de corrida atual, então venho achando os peixes muito altos "
    "para o que eu consigo fazer ou os treinos muito leve, poucas distâncias, etc.,"
)

_TOO_SLOW = (
    "eu estou querendo colocar uma corrida mais na semana porque eu acho que eu estou demorando "
    "muito para chegar ao meu objetivo"
)

_CHECKIN_NOTE = (
    "Atleta acha as metas e distâncias muito baixas para o seu ritmo atual, achando os treinos "
    "leves."
)


def test_the_real_phrases_are_recognised():

    for text in (
        _TOO_EASY, _TOO_SLOW, _CHECKIN_NOTE,
        "tá muito fácil, aguento mais", "os treinos estão fracos", "queria mais treino",
        "dá pra puxar mais?", "acho os treinos muito leves",
    ):

        assert says_more(text), text


def test_the_rest_of_what_he_said_is_not_a_request():
    """Dúvida, relato de uma sessão, troca de dia ou comentário não são pedido de mais carga."""

    for text in (
        "Quero baixar o app", "Duvida, o que quer dizer fartlek? É mesma coisa que tiro?",
        "Hoje eu tive que fazer meu treino na esteira. Prejudicado.",
        "Para a próxima semana, eu quero começar a correr três vezes por semana",
        "Eu só acho que quase sempre a minha meta de pace é acima do 6",
        "o treino de hoje foi leve", "SIM", "", None,
        # o TIPO de treino ("rodagem leve", "pace leve") não é queixa — pedidos reais de 27/09
        "Ajusta os pace leve pra 6:20-6:50 em todos os treinos", "faz o treino leve na terça",
        "meu ritmo leve é 6:50",
        # a negação inverte: "não dá pra aumentar" / "não aguento mais" não pedem mais carga
        "N da pra aumentar um pouco?", "não dá pra puxar mais essa semana",
        "não aguento mais esse calor", "nao posso aumentar o volume",
    ):

        assert not says_more(text), text


def _turn(day: str, text: str, role: str = "user") -> dict:

    return {"role": role, "timestamp": f"{day}T12:00:00-03:00", "text": text}


class _Checkin:

    def __init__(self, day, note):

        self.day, self.note = day, note


def test_find_reads_conversation_and_checkins_inside_the_window():

    today = date(2026, 10, 21)

    asks = find(
        [
            _turn("2026-10-02", _TOO_EASY),
            _turn("2026-10-18", _TOO_SLOW),
            # o coach falando não conta, e fora da janela de 28 dias também não
            _turn("2026-10-10", "os treinos estão leves mesmo", role="assistant"),
            _turn("2026-09-10", "tá tudo muito fácil"),
        ],
        [_Checkin("2026-10-02", _CHECKIN_NOTE), _Checkin("2026-10-03", "dor no joelho")],
        today,
    )

    assert [(a.day, a.source) for a in asks] == [
        (date(2026, 10, 2), "conversa"),
        (date(2026, 10, 2), "check-in"),
        (date(2026, 10, 18), "conversa"),
    ]


def test_a_long_message_is_quoted_short():

    asks = find([_turn("2026-10-18", "acho os treinos leves " + "treino " * 80)],
                [], date(2026, 10, 21))

    assert len(asks[0].quote) <= 150 and asks[0].quote.endswith("…")


def _runs(*weeks):
    """(semana, km) -> corridas na segunda-feira de cada semana (a 1ª = 07/09/2026)."""

    start = datetime(2026, 9, 7, 7, 0)

    return [
        make_activity(id=i, start_date=start + timedelta(weeks=w), distance=km * 1000)
        for i, (w, km) in enumerate(weeks)
    ]


def test_the_dose_before_and_after_the_request():
    """Pedido em 02/10 (semana de 28/09). Antes: semanas de 07, 14 e 21/09. Depois: de 28/09 até a
    última semana fechada (a de 19/10 está em andamento em 21/10)."""

    acts = _runs((0, 8.3), (1, 10.0), (2, 7.5), (3, 5.2), (4, 9.0), (5, 8.0))

    since = dose_since(acts, date(2026, 10, 2), date(2026, 10, 21))

    assert round(since["before_week"], 1) == round((8.3 + 10.0 + 7.5) / 3, 1)
    assert since["before_long"] == 10.0
    assert round(since["after_week"], 1) == round((5.2 + 9.0 + 8.0) / 3, 1)
    assert since["after_long"] == 9.0

    # sem semana depois (ou antes) não há o que comparar
    assert dose_since(acts[:3], date(2026, 10, 2), date(2026, 10, 21)) is None


_ASKS = [Ask(date(2026, 10, 2), "treinos muito leve, poucas distâncias", "conversa"),
         Ask(date(2026, 10, 18), "demorando muito para chegar ao meu objetivo", "conversa")]

_SINCE = {"before_week": 8.6, "before_long": 10.0, "after_week": 7.4, "after_long": 9.0}


def test_the_plan_directive_quotes_him_weighs_the_numbers_and_demands_an_answer():

    text = asks_more_directive(
        _ASKS, [2, 3, 2, 3, 4, 3, 3], 0, "equilibrado (carga ótima + recuperado)", _SINCE,
    )

    assert text.startswith("ELE PEDE MAIS")
    assert 'em 02/10 (conversa) "treinos muito leve, poucas distâncias"' in text
    assert "esforço percebido ≤3/10 em 6 de 7 corridas recentes" in text
    assert "0% do tempo em zona forte" in text and "corpo: equilibrado" in text
    assert "Antes do pedido: ~9 km/semana" in text and "Desde então: ~7 km/semana" in text
    # a resposta é dose se os números sustentam, o dado se não — e nunca o silêncio
    assert "a resposta é DOSE" in text and "diga isso a ele com o dado" in text
    assert "Deixar a semana igual sem dizer nada é o único erro" in text


def test_the_directive_does_not_hide_a_body_that_contradicts_the_request():
    """O pedido pesa JUNTO do corpo: esforço alto e corpo sobrecarregado aparecem nos números."""

    text = asks_more_directive(
        _ASKS[-1:], [7, 8, 7], 40, "sobrecarregado (carga alta + recuperação caindo)", None,
    )

    assert "esforço percebido ≤3/10 em 0 de 3" in text
    assert "corpo: sobrecarregado" in text
    assert "recuperação caindo" in text


def test_the_fact_for_the_other_voices_is_short_and_does_not_promise():

    text = asks_more_fact(_ASKS, [2, 3, 3], 0, _SINCE)

    assert text.startswith('Ele pediu mais em 18/10: "demorando muito para chegar ao meu objetivo"')
    assert "esforço percebido ≤3/10 em 3 de 3" in text
    assert "não prometa mudança que o plano não fez" in text
    assert "ELE PEDE MAIS" not in text

    assert asks_more_directive([], [], None, None, None) == ""
    assert asks_more_fact([], [], None, None) == ""
