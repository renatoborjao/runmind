"""O nome da prova refina quando a MESMA prova (mesma data) chega com um nome
melhor. Caso real — Leonardo, 18/10: contou da prova ("tem trajeto de 10 e 15 km")
e a lista gravou "Corrida 10km/15km"; minutos depois mandou o link e o coach
confirmou "TF Sports Villa Lobos III", mas a lista nunca trocou o nome. Ele pediu
pra ajustar na aba Treino e o coach respondeu que já estava certo (não estava)."""

from datetime import date
from unittest.mock import patch

import pytest

from app.application.coach.conversation.coach_brain import BrainAction
from app.application.coach.conversation.goal_action_executor import (
    GoalActionExecutor,
)
from app.application.races.race_service import RaceService
from app.domain.value_objects.race_name import proper_core, refined_name

R = "app.application.races.race_service"

TODAY = date(2026, 10, 18)

DEC20 = "2026-12-20"


def _today():

    return patch(f"{R}.today_local", return_value=TODAY)


# ---- a regra pura ------------------------------------------------------------


@pytest.mark.parametrize(
    "name,core",
    [
        ("Corrida 10km/15km", ""),
        ("15 km", ""),
        ("Meia Maratona", ""),
        ("Prova", ""),
        ("TF Sports Villa Lobos III (10 km)", "tf sports villa lobos iii"),
        ("Santander … Villa-Lobos (15 km)", "santander villa-lobos"),
    ],
)
def test_proper_core_drops_distance_and_generic_words(name, core):

    assert proper_core(name) == core


def test_generic_current_name_yields_to_a_specific_one():

    assert (
        refined_name("Corrida 10km/15km", "TF Sports Villa Lobos III (10 km)")
        == "TF Sports Villa Lobos III (10 km)"
    )

    assert refined_name("15 km", "Villa-Lobos (15 km)") == "Villa-Lobos (15 km)"


def test_a_generic_name_never_replaces_a_real_one():

    assert refined_name("TF Sports Villa Lobos III (10 km)", "10 km") is None
    assert refined_name("TF Sports Villa Lobos III (10 km)", "Corrida 10km") is None
    assert refined_name("TF Sports Villa Lobos III (10 km)", None) is None
    assert refined_name("TF Sports Villa Lobos III (10 km)", "") is None


def test_a_shorter_version_of_the_same_name_does_not_downgrade():

    assert (
        refined_name("TF Sports Villa Lobos III (10 km)", "Villa Lobos (10 km)")
        is None
    )

    assert refined_name("Villa-Lobos (15 km)", "Villa-Lobos (15 km)") is None


def test_a_name_that_extends_the_current_one_wins():

    assert (
        refined_name("Villa-Lobos (15 km)", "Santander Villa-Lobos (15 km)")
        == "Santander Villa-Lobos (15 km)"
    )


def test_two_different_real_names_for_the_same_day_latest_wins():
    """Ninguém corre duas provas no mesmo dia: o nome novo é o atleta corrigindo."""

    assert (
        refined_name("Corrida do Parque (10 km)", "Meia de Floripa (10 km)")
        == "Meia de Floripa (10 km)"
    )


# ---- na lista de provas ------------------------------------------------------


def test_leonardo_case_link_message_renames_the_listed_race():
    """O 1º papo cria "Corrida 10km/15km"; o 2º (o link, mesma data) tem o nome
    certo — a lista passa a ter UMA prova, com o nome certo e a distância dita."""

    with _today():

        RaceService.record_from_conversation(
            "leo", "Corrida 10km/15km", DEC20, target_time="01:00:00",
            distance_km=10.0,
        )

        RaceService.record_from_conversation(
            "leo", "TF Sports Villa Lobos III (10 km)", DEC20,
            target_time="01:00:00", distance_km=10.0, priority="A",
        )

        races = RaceService.list("leo")

    assert len(races) == 1
    assert races[0]["name"] == "TF Sports Villa Lobos III (10 km)"
    assert races[0]["distance_km"] == 10.0
    assert races[0]["priority"] == "A"


def test_generic_mention_later_keeps_the_real_name():

    with _today():

        RaceService.record_from_conversation(
            "leo", "TF Sports Villa Lobos III (10 km)", DEC20,
        )

        RaceService.record_from_conversation("leo", "10 km", DEC20)

        races = RaceService.list("leo")

    assert [r["name"] for r in races] == ["TF Sports Villa Lobos III (10 km)"]


def test_other_dates_are_untouched():

    with _today():

        RaceService.record_from_conversation("leo", "Corrida 10km/15km", DEC20)

        RaceService.record_from_conversation(
            "leo", "Meia de SP (21 km)", "2027-04-04",
        )

        names = {r["date"]: r["name"] for r in RaceService.list("leo")}

    assert names == {DEC20: "Corrida 10km/15km", "2027-04-04": "Meia de SP (21 km)"}


def test_brain_goal_action_renames_through_the_executor():
    """O caminho vivo: a ação `goal` do cérebro (com race_name resolvido) chega na
    lista pelo executor — é por ele que o link do Leonardo entrou às 12:04."""

    from unittest.mock import MagicMock

    from tests.coach.factories import make_runner

    runner = make_runner(race_date=None, target_race=None, target_time=None)

    # perfil sem âncora: a leitura da lista não importa nada dele
    profile_repo = MagicMock()

    profile_repo.load.return_value = MagicMock(
        race_date=None, target_race=None, target_time=None,
    )

    with (
        _today(),
        patch(f"{R}.RunnerProfileRepository", return_value=profile_repo),
        patch(
            "app.application.coach.conversation.goal_action_executor.RunnerMemoryService"
        ),
    ):

        RaceService.record_from_conversation("leo", "Corrida 10km/15km", DEC20)

        action = BrainAction(
            type="goal", scope="week", target_day=None,
            instruction="correr os 10 km da Villa Lobos em 1h",
            race_name="TF Sports Villa Lobos III", distance_km=10.0,
            race_date=DEC20, target_time="01:00:00", relationship="primary",
        )

        GoalActionExecutor._register_one(MagicMock(), "leo", runner, action)

        races = RaceService.list("leo")

    assert [r["name"] for r in races] == ["TF Sports Villa Lobos III (10 km)"]
