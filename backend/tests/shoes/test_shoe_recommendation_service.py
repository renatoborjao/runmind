from types import SimpleNamespace
from unittest.mock import patch

from app.application.shoes.shoe_recommendation_service import (
    ShoeRecommendationService,
)
from app.domain.entities.shoe import Shoe, ShoeBook, ShoeRule
from app.infrastructure.persistence.shoe_repository import ShoeRepository

MOD = "app.application.shoes.shoe_recommendation_service"


def _session(workout_type, day="Monday"):

    return SimpleNamespace(workout_type=workout_type, day=day)


def _rec(book, session):

    return ShoeRecommendationService.recommend(book, session)


def test_rule_drives_recommendation():

    book = ShoeBook(
        shoes=[
            Shoe(id="boston", name="Boston", category="dia a dia",
                 is_default=True),
            Shoe(id="vapor", name="Vaporfly", category="prova"),
        ],
        rules=[ShoeRule(match="tiro", shoe_id="vapor")],
    )

    shoe, reason = _rec(book, _session("Tiros"))

    assert shoe.id == "vapor"
    assert "tiro" in reason


def test_quality_picks_prova_bucket():

    book = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", category="dia a dia", is_default=True),
        Shoe(id="vapor", name="Vaporfly", category="prova"),
    ])

    shoe, _ = _rec(book, _session("Fartlek"))

    assert shoe.id == "vapor"


def test_easy_run_uses_daily():

    book = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", category="dia a dia", is_default=True),
        Shoe(id="vapor", name="Vaporfly", category="prova"),
    ])

    shoe, reason = _rec(book, _session("Rodagem leve"))

    assert shoe.id == "boston"
    assert "rodagem" in reason.lower()


def test_long_run_stays_on_daily_even_progressive():

    book = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", category="dia a dia", is_default=True),
        Shoe(id="vapor", name="Vaporfly", category="prova"),
    ])

    shoe, reason = _rec(book, _session("Longão Progressivo"))

    assert shoe.id == "boston"
    assert "longão" in reason.lower()


def test_rotation_varies_daily_shoes_across_days():
    """Com vários pares do dia a dia, dias diferentes pegam pares diferentes."""

    book = ShoeBook(shoes=[
        Shoe(id="a", name="A", category="dia a dia"),
        Shoe(id="b", name="B", category="dia a dia"),
    ])

    mon = _rec(book, _session("Rodagem", day="Monday"))[0]     # idx 0
    tue = _rec(book, _session("Rodagem", day="Tuesday"))[0]    # idx 1

    assert mon.id != tue.id
    assert "revezando" in _rec(book, _session("Rodagem"))[1]


def test_rotation_favors_freshest_on_first_index():

    book = ShoeBook(shoes=[
        Shoe(id="rodado", name="Rodado", category="dia a dia",
             initial_km=400.0),
        Shoe(id="novo", name="Novo", category="dia a dia", initial_km=20.0),
    ])

    # Monday -> idx 0 sobre a lista ordenada do mais NOVO pro mais rodado
    shoe, _ = _rec(book, _session("Rodagem", day="Monday"))

    assert shoe.id == "novo"


def test_rule_forced_worn_shoe_swaps_to_fresher():
    """Regra aponta um par GASTO -> troca pelo mais novo do mesmo balde."""

    book = ShoeBook(
        shoes=[
            Shoe(id="boston", name="Boston", category="dia a dia",
                 initial_km=720.0, alert_threshold_km=700.0),
            Shoe(id="novo", name="Novo", category="dia a dia",
                 initial_km=50.0),
        ],
        rules=[ShoeRule(match="rodagem", shoe_id="boston")],
    )

    shoe, reason = _rec(book, _session("Rodagem"))

    assert shoe.id == "novo"
    assert "poupar" in reason and "Boston" in reason


def test_assignment_overrides_recommendation_for_that_date():
    """'quero o Red Hare no domingo' sobrepõe a recomendação SÓ naquela data."""

    book = ShoeBook(
        shoes=[
            Shoe(id="vomero", name="Vomero", category="dia a dia",
                 is_default=True),
            Shoe(id="red", name="Red Hare", category="dia a dia"),
        ],
        assignments={"2026-08-30": "red"},
    )

    session = _session("Longão Progressivo", day="Sunday")

    # com a data fixada -> o par escolhido pelo atleta
    shoe, reason = ShoeRecommendationService.recommend(
        book, session, "2026-08-30"
    )
    assert shoe.id == "red"
    assert "pediu" in reason

    # OUTRA data (sem assignment) -> recomendação normal, sem o "você pediu"
    _, other_reason = ShoeRecommendationService.recommend(
        book, session, "2026-09-06"
    )
    assert "pediu" not in other_reason


def test_retired_assigned_shoe_is_ignored():

    book = ShoeBook(
        shoes=[
            Shoe(id="vomero", name="Vomero", category="dia a dia",
                 is_default=True),
            Shoe(id="red", name="Red Hare", category="dia a dia", retired=True),
        ],
        assignments={"2026-08-30": "red"},
    )

    shoe, _ = ShoeRecommendationService.recommend(
        book, _session("Longão", day="Sunday"), "2026-08-30"
    )

    assert shoe.id == "vomero"  # ignora o aposentado, recomenda normal


def test_quality_uses_versatil_when_no_prova():
    """Fartlek sem racer -> pega o SUPER TRAINER (versátil), não o dia a dia."""

    book = ShoeBook(shoes=[
        Shoe(id="nova", name="Novablast", category="dia a dia", is_default=True),
        Shoe(id="sonic", name="Sonicblast", category="versátil"),
    ])

    shoe, reason = _rec(book, _session("Fartlek"))

    assert shoe.id == "sonic"
    assert "super trainer" in reason


def test_rapido_label_is_the_fast_bucket_and_reason():
    """Rótulo atual 'rápido' = balde veloz; a fala diz 'par rápido' (não
    'prova'). E 'prova' segue aceito como sinônimo (dado antigo)."""

    book = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", category="dia a dia", is_default=True),
        Shoe(id="evo", name="Evo SL", category="rápido"),
    ])

    shoe, reason = _rec(book, _session("Tempo Run"))

    assert shoe.id == "evo"
    assert "rápido" in reason
    assert "prova" not in reason

    # retrocompat: um par salvo como 'prova' ainda cai no balde veloz
    legacy = ShoeBook(shoes=[
        Shoe(id="boston", name="Boston", category="dia a dia", is_default=True),
        Shoe(id="vapor", name="Vaporfly", category="prova"),
    ])

    assert _rec(legacy, _session("Tiros"))[0].id == "vapor"


def test_prova_beats_versatil_on_quality():

    book = ShoeBook(shoes=[
        Shoe(id="evo", name="Evo SL", category="prova"),
        Shoe(id="red", name="Red Hare", category="versátil"),
        Shoe(id="vom", name="Vomero", category="dia a dia", is_default=True),
    ])

    shoe, _ = _rec(book, _session("Tempo Run"))

    assert shoe.id == "evo"


def test_versatil_rotates_with_daily_on_long_and_easy():
    """O versátil (super trainer) NÃO fica reservado: reveza JUNTO com o dia a
    dia no longão/rodagem — o Red Hare vale pra longão E rodagem (Renato)."""

    book = ShoeBook(shoes=[
        Shoe(id="vom", name="Vomero", category="dia a dia", initial_km=300.0),
        Shoe(id="red", name="Red Hare", category="versátil", initial_km=8.0),
    ])

    # os dois revezam pelo dia; o mais NOVO (Red Hare) sai primeiro
    mon = _rec(book, _session("Longão", day="Monday"))[0].id
    tue = _rec(book, _session("Longão", day="Tuesday"))[0].id

    assert mon == "red"                 # versátil elegível e freshest-first
    assert {mon, tue} == {"red", "vom"}  # os dois na rotação, nenhum de fora
    # vale também pra rodagem
    assert _rec(book, _session("Rodagem", day="Monday"))[0].id == "red"


def test_versatil_covers_long_when_no_daily():
    """Sem trainer de conforto, o versátil cobre o longão."""

    book = ShoeBook(shoes=[
        Shoe(id="red", name="Red Hare", category="versátil", is_default=True),
    ])

    shoe, _ = _rec(book, _session("Longão", day="Sunday"))

    assert shoe.id == "red"


def test_rotation_by_position_spreads_across_fleet():
    """Com os treinos da semana, os 2 treinos fáceis pegam pares DIFERENTES
    (1º fácil -> par 1, 2º fácil -> par 2), não o mesmo por paridade de dia."""

    book = ShoeBook(shoes=[
        Shoe(id="neo", name="Neo Vista", category="dia a dia", initial_km=100.0),
        Shoe(id="nova", name="Novablast", category="dia a dia", initial_km=50.0),
    ])

    tue = _session("Fartlek", "Tuesday")     # qualidade
    thu = _session("Rodagem leve", "Thursday")  # 1º fácil
    sat = _session("Longão", "Saturday")     # 2º fácil
    week = [tue, thu, sat]

    thu_pick = ShoeRecommendationService.recommend(
        book, thu, week_sessions=week
    )[0]
    sat_pick = ShoeRecommendationService.recommend(
        book, sat, week_sessions=week
    )[0]

    assert thu_pick.id == "nova"   # 1º fácil -> mais novo
    assert sat_pick.id == "neo"    # 2º fácil -> o outro
    assert thu_pick.id != sat_pick.id


def test_rodagem_por_tempo_is_easy_not_quality():
    """'Rodagem por Tempo' (medida em minutos) NÃO é tempo run — rodagem é
    fácil e pega o dia a dia, não o par rápido."""

    book = ShoeBook(shoes=[
        Shoe(id="vom", name="Vomero", category="dia a dia", is_default=True),
        Shoe(id="evo", name="Evo SL", category="rápido"),
    ])

    shoe, reason = _rec(book, _session("Rodagem por Tempo"))

    assert shoe.id == "vom"
    assert "forte" not in reason


def test_rodagem_progressiva_stays_easy():
    """'Rodagem Progressiva' segue rodagem (fácil), apesar do 'progress'."""

    book = ShoeBook(shoes=[
        Shoe(id="vom", name="Vomero", category="dia a dia", is_default=True),
        Shoe(id="evo", name="Evo SL", category="rápido"),
    ])

    assert _rec(book, _session("Rodagem Progressiva"))[0].id == "vom"


def test_no_shoes_returns_none():

    assert _rec(ShoeBook(), _session("x")) is None


def test_single_shoe_is_always_the_pick():

    book = ShoeBook(shoes=[Shoe(id="one", name="Único")])

    shoe, _ = _rec(book, _session("Tiros"))

    assert shoe.id == "one"


def test_line_is_silent_without_shoes(tmp_path):

    repo = ShoeRepository()
    repo.storage = tmp_path

    with patch(f"{MOD}.ShoeRepository", return_value=repo):

        assert ShoeRecommendationService.line("renato", _session("Tiros")) == ""


def test_line_formats_suggestion(tmp_path):

    repo = ShoeRepository()
    repo.storage = tmp_path
    repo.save("renato", ShoeBook(shoes=[
        Shoe(id="boston", name="Adidas Boston", nickname="Boston",
             category="dia a dia", is_default=True),
    ]))

    with patch(f"{MOD}.ShoeRepository", return_value=repo):

        line = ShoeRecommendationService.line("renato", _session("Rodagem leve"))

    assert line.startswith("👟 Sugestão de tênis: Boston")


def test_line_remembers_recommendation_for_the_date(tmp_path):
    """A sugestão MOSTRADA fica gravada por data -> a atribuição conta nela
    depois (fecha o 'recomendou X, contou no padrão')."""

    from datetime import date

    repo = ShoeRepository()
    repo.storage = tmp_path
    repo.save("renato", ShoeBook(shoes=[
        Shoe(id="vomero", name="Vomero", category="dia a dia", is_default=True),
        Shoe(id="evo", name="Evo SL", category="versátil"),
    ]))

    with patch(f"{MOD}.ShoeRepository", return_value=repo):

        ShoeRecommendationService.line(
            "renato", _session("Tempo"), session_date=date(2026, 9, 1)
        )

    book = repo.load("renato")
    assert book.recommended["2026-09-01"] == "evo"   # o versátil sugerido


def test_line_remembers_when_date_is_iso_string(tmp_path):
    """REGRESSÃO: os callers reais (formatters) passam a data como STRING ISO,
    não como date. Antes, `_remember` chamava `.isoformat()` na string e o line
    inteiro estourava no except -> tênis sumia do lembrete E nada era lembrado
    pra a atribuição (o bug 'não veio o tênis' + 'contou no Vomero')."""

    repo = ShoeRepository()
    repo.storage = tmp_path
    repo.save("renato", ShoeBook(shoes=[
        Shoe(id="vomero", name="Vomero", category="dia a dia", is_default=True),
        Shoe(id="evo", name="Evo SL", category="versátil"),
    ]))

    with patch(f"{MOD}.ShoeRepository", return_value=repo):

        line = ShoeRecommendationService.line(
            "renato", _session("Rodagem por Tempo"),
            session_date="2026-09-04",  # STRING, como o formatter passa
        )

    # a sugestão SAI (não engoliu no except)
    assert line.startswith("👟 Sugestão de tênis:")
    # e ficou lembrada pra a data (a atribuição vai contar nela)
    assert repo.load("renato").recommended["2026-09-04"] in {"vomero", "evo"}


def test_line_without_date_does_not_persist(tmp_path):

    repo = ShoeRepository()
    repo.storage = tmp_path
    repo.save("renato", ShoeBook(shoes=[
        Shoe(id="vomero", name="Vomero", category="dia a dia", is_default=True),
    ]))

    with patch(f"{MOD}.ShoeRepository", return_value=repo):

        ShoeRecommendationService.line("renato", _session("Rodagem"))

    assert repo.load("renato").recommended == {}
