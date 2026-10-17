"""Prova estruturada vinda da CONVERSA e do CADASTRO: entra na lista (calendário do
coach) com distância e papel, sem efeito colateral no perfil/memória, e a sugestão
de papel respeita o que o atleta já escolheu. Casos reais: renato2 (meia + 15 km)
e mauricio (15 km + uma principal nova)."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.conversation.coach_brain import BrainAction
from app.application.coach.conversation.goal_action_executor import (
    GoalActionExecutor,
)
from app.application.races.race_service import RaceService
from app.infrastructure.persistence.race_repository import RaceRepository
from tests.coach.factories import make_runner

R = "app.application.races.race_service"
G = "app.application.coach.conversation.goal_action_executor"

TODAY = date(2026, 10, 17)

HALF = "2027-04-04"
FIFTEEN = "2026-12-20"


def _today():

    return patch(f"{R}.today_local", return_value=TODAY)


def _by_name(profile="p"):

    return {r["name"]: r for r in RaceService.list(profile)}


# ---- registro direto --------------------------------------------------------


def test_future_race_is_recorded_with_distance_role_and_target():

    with _today():

        rec = RaceService.record_from_conversation(
            "p", "Meia de SP (21 km)", HALF, target_time="1:59:59",
            distance_km=21.0975, priority="A",
        )

        assert rec["priority"] == "A" and rec["distance_km"] == 21.0975
        assert rec["target_time"] == "1:59:59"

        listed = _by_name()["Meia de SP (21 km)"]

        assert listed["priority_effective"] == "A"


def test_same_race_twice_is_not_duplicated_and_fills_what_was_missing():

    with _today():

        RaceService.record_from_conversation("p", "15 km", FIFTEEN)
        RaceService.record_from_conversation(
            "p", "15 km", FIFTEEN, target_time="1:15:00", priority="B",
        )

        races = RaceService.list("p")

        assert len(races) == 1
        assert races[0]["priority"] == "B"


def test_past_or_dateless_race_is_ignored_and_never_raises():

    with _today():

        assert RaceService.record_from_conversation("p", "10 km", "2026-09-19") is None
        assert RaceService.record_from_conversation("p", "10 km", None) is None
        assert RaceService.list("p") == []


def test_new_principal_demotes_the_other_chosen_principal():

    with _today():

        RaceService.record_from_conversation("p", "15 km", FIFTEEN, priority="A")
        RaceService.record_from_conversation("p", "Meia (21 km)", HALF, priority="A")

        by = _by_name()

        assert by["Meia (21 km)"]["priority"] == "A"
        assert by["15 km"]["priority"] == "B"


def test_suggestion_never_creates_a_second_principal():
    """O atleta escolheu a 10 km como principal; a meia (mais longa) NÃO vira
    'sugerida A' por cima — sem escolha, é preparatória."""

    with _today():

        RaceService.record_from_conversation(
            "p", "10 km", FIFTEEN, distance_km=10.0, priority="A",
        )
        RaceService.record_from_conversation("p", "Meia (21 km)", HALF)

        by = _by_name()

        assert by["10 km"]["priority_effective"] == "A"
        assert by["Meia (21 km)"]["priority_suggested"] == "B"
        assert by["Meia (21 km)"]["priority_effective"] == "B"


# ---- pelo cérebro do coach (ação goal) ---------------------------------------


def _goal(**kw) -> BrainAction:

    base = dict(type="goal", scope="single_session", target_day=None, instruction="")
    base.update(kw)

    return BrainAction(**base)


def _apply(actions, runner=None):
    """Roda o executor com perfil/memória/plano mockados (a lista de provas é a
    REAL, no storage temporário do conftest)."""

    ctx = [
        patch(f"{G}.RunnerProfileRepository", return_value=MagicMock()),
        patch(f"{G}.RunnerMemoryService.process", new=MagicMock()),
        patch(
            f"{G}.CurrentPlanProvider.for_profile",
            new=AsyncMock(return_value=(make_runner(), MagicMock())),
        ),
        patch(f"{G}.today_local", return_value=TODAY),
        _today(),
    ]

    for c in ctx:
        c.start()

    try:
        return asyncio.run(
            GoalActionExecutor.apply_many(
                "p", runner or make_runner(), actions, regenerate=False,
            )
        )
    finally:
        for c in reversed(ctx):
            c.stop()


def test_brain_primary_and_stepping_stone_become_roles_A_and_B():
    """Renato: 'a meia é minha principal; o 15 km é só um degrau' — uma mensagem,
    duas ações: a lista fica com meia = A e 15 km = B."""

    _apply([
        _goal(
            race_name="Meia Maratona de SP", distance_km=21.0975, race_date=HALF,
            target_time="1:59:59", relationship="primary",
            instruction="meia abaixo de 2h",
        ),
        _goal(
            race_name="Villa-Lobos", distance_km=15.0, race_date=FIFTEEN,
            target_time="1:15:00", relationship="stepping_stone",
            instruction="15 km em 1h15",
        ),
    ])

    with _today():

        races = RaceService.list("p")

    roles = {r["date"]: r["priority"] for r in races}

    assert roles == {FIFTEEN: "B", HALF: "A"}

    by_date = {r["date"]: r for r in races}

    assert by_date[HALF]["distance_km"] == 21.0975
    assert by_date[FIFTEEN]["name"] == "Villa-Lobos (15 km)"


def test_brain_additional_race_enters_without_a_role():
    """'Também quero fazer uma 10k em novembro': soma ao calendário e deixa o
    papel pra sugestão/atleta (nada de chutar principal)."""

    _apply([
        _goal(
            race_name="Corrida de Novembro", distance_km=10.0,
            race_date="2026-11-22", relationship="additional",
            instruction="10 km em novembro",
        ),
    ])

    with _today():

        race = RaceService.list("p")[0]

    assert race["priority"] is None
    assert race["distance_km"] == 10.0


def test_goal_without_a_race_date_does_not_touch_the_list():

    _apply([_goal(instruction="quero ser mais saudável", relationship="replace")])

    with _today():

        assert RaceService.list("p") == []


# ---- o mesmo evento com nomes diferentes (caso real do renato2) ---------------


LONG_NAME = "Santander Track&Field Run Series - Villa-Lobos (15 km)"


def test_same_date_different_name_is_the_same_event_not_a_duplicate():
    """O app chama de 'Santander … Villa-Lobos (15 km)'; na conversa vira
    'Villa-Lobos (15 km)'. Mesma data = mesma prova: um registro só, com o
    nome original e o papel novo."""

    # a prova já estava na lista (cadastrada pelo app)
    RaceRepository().add("p", LONG_NAME, FIFTEEN, "1:15:00")

    _apply([
        _goal(
            race_name="Villa-Lobos", distance_km=15.0, race_date=FIFTEEN,
            target_time="1:15:00", relationship="stepping_stone",
            instruction="15 km em 1h15",
        ),
    ])

    with _today():

        races = RaceService.list("p")

    assert [r["name"] for r in races] == [LONG_NAME]
    assert races[0]["priority"] == "B"


def test_profile_anchor_with_another_name_is_not_imported_twice():
    """A âncora do perfil ('Villa-Lobos (15 km)') não duplica a prova da lista
    que já está na mesma data com o nome comprido."""

    from types import SimpleNamespace

    RaceRepository().add("p", LONG_NAME, FIFTEEN, "1:15:00")

    runner = SimpleNamespace(
        race_date=FIFTEEN, target_race="Villa-Lobos (15 km)", target_time="1:15:00",
    )

    with _today(), patch(
        f"{R}.RunnerProfileRepository",
        return_value=MagicMock(load=MagicMock(return_value=runner)),
    ):

        races = RaceService.list("p")

    assert len(races) == 1
