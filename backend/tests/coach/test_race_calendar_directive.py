"""CALENDÁRIO de provas — o coach vê todas as provas à frente com papel e
distância (casos reais: renato2 15 km + meia; mauricio 10 km passada + 15 km)."""

from datetime import date

from app.application.coach.planning.race_calendar_directive import (
    future_races,
    has_calendar,
    race_calendar_directive,
    race_list_line,
)

TODAY = date(2026, 10, 17)


def _race(name, when, km, priority=None, suggested=None, target=None):

    return {
        "id": name, "name": name, "date": when, "distance_km": km,
        "target_time": target, "priority": priority,
        "priority_suggested": suggested,
        "priority_effective": priority or suggested,
    }


RENATO = [
    _race("Villa-Lobos (15 km)", "2026-12-20", 15.0, suggested="B", target="1:15:00"),
    _race("Meia Maratona SP (21 km)", "2027-04-04", 21.0975, suggested="A", target="1:59:59"),
]

MAURICIO = [
    _race("10 km", "2026-09-19", 10.0, target="00:57:00"),   # já passou
    _race("15 km", "2026-12-20", 15.0, suggested="A", target="01:22:30"),
]


def test_renato_gets_the_full_calendar_with_gap_and_roles():

    text = race_calendar_directive(RENATO, TODAY)

    assert text.startswith("CALENDÁRIO DE PROVAS")
    assert "2 prova(s)" in text
    # ordem por data, distância, alvo, semanas e papel
    first = text.index("20/12/2026")
    second = text.index("04/04/2027")
    assert first < second
    assert "15 km · alvo 1:15:00 · em 9 semana(s)" in text
    assert "PREPARATÓRIA (B), sugerido" in text
    assert "21.1 km · alvo 1:59:59 · em 24 semana(s) · 15 sem. depois da anterior" in text
    assert "PRINCIPAL (A), sugerido" in text
    # conhecimento + aviso dos sinais automáticos + nota do 'sugerido'
    assert "MINI-polimento" in text
    assert "PRÓXIMA prova" in text
    assert "ainda não confirmou" in text
    # compacto: vai em toda mensagem do coach (custo de tokens)
    assert len(text) < 1900


def test_mauricio_with_one_future_race_has_no_calendar():
    """A 10 km já passou: sobra uma prova, sem papel B/C escolhido → nada muda."""

    assert not has_calendar(MAURICIO, TODAY)
    assert race_calendar_directive(MAURICIO, TODAY) == ""
    assert [r["name"] for r in future_races(MAURICIO, TODAY)] == ["15 km"]


def test_single_race_the_athlete_marked_preparatory_does_show_the_calendar():
    """Escolha explícita B/C numa prova só muda como o plano a trata."""

    races = [_race("15 km", "2026-12-20", 15.0, priority="B")]

    text = race_calendar_directive(races, TODAY)

    assert "PREPARATÓRIA (B)" in text and "sugerido" not in text.split("PAPÉIS:")[0]


def test_chosen_role_is_not_flagged_as_suggested():

    races = [
        _race("A", "2026-12-20", 15.0, priority="A", suggested="B"),
        _race("B", "2027-04-04", 21.0975, priority="C", suggested="A"),
    ]

    text = race_calendar_directive(races, TODAY)

    assert "PRINCIPAL (A)" in text and "DE TREINO (C)" in text
    # o atleta escolheu as duas: sem a nota de 'sugerido'
    assert "ainda não confirmou" not in text


def test_unknown_role_is_left_to_the_coach():

    races = [
        _race("Corrida do Bairro", "2026-12-20", None),
        _race("Corrida da Praça", "2027-03-01", None),
    ]

    text = race_calendar_directive(races, TODAY)

    assert text.count("papel: não definido (decida pelo contexto)") == 2


def test_race_today_still_counts_and_past_is_dropped():

    races = [
        _race("Hoje", "2026-10-17", 10.0, suggested="B"),
        _race("Ontem", "2026-10-16", 5.0),
        _race("Depois", "2027-01-17", 21.0975, suggested="A"),
    ]

    text = race_calendar_directive(races, TODAY)

    assert "Hoje" in text and "Depois" in text and "Ontem" not in text
    assert "esta semana" in text


def test_single_race_shows_its_name_as_the_athlete_sees_it_in_the_app():
    """Leonardo 18/10: reclamou do NOME na aba Treino ("Corrida 10km/15km") e o coach, que só
    via distância e data, respondeu "já está certinha". Com uma prova só, o dossiê agora traz o
    nome da lista."""

    leonardo = [_race("Corrida 10km/15km", "2026-12-20", 10.0, target="01:00:00")]

    line = race_list_line(leonardo, TODAY)

    assert "o nome que o atleta vê na aba Treino): Corrida 10km/15km — 20/12/2026 · 10 km" in line
    assert "ANTES de afirmar que está certo" in line


def test_the_list_name_is_left_out_when_the_calendar_already_names_the_races():

    # duas provas à frente: o calendário já traz cada nome
    assert race_list_line(RENATO, TODAY) == ""

    # uma prova que ele marcou B/C também vira calendário
    assert race_list_line([_race("5 km", "2026-11-01", 5.0, priority="B")], TODAY) == ""


def test_the_list_name_needs_a_race_ahead():

    assert race_list_line([], TODAY) == ""

    assert race_list_line([_race("10 km", "2026-09-19", 10.0)], TODAY) == ""

    # sem distância guardada a linha não inventa uma
    assert "km" not in race_list_line([_race("Prova do bairro", "2026-12-20", None)], TODAY)
