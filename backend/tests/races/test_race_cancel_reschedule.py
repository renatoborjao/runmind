"""Prova CANCELADA ou REMARCADA pela conversa: a lista de provas (o calendário que
o coach lê) acompanha — sem prova fantasma, sem duplicata e sem tirar a prova
errada. Casos reais: renato2 (15 km em 20/12 + meia em 04/04/2027)."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from app.application.coach.memory.memory_extraction_engine import (
    MemoryExtractionEngine,
)
from app.application.coach.memory.runner_memory_service import RunnerMemoryService
from app.application.races.race_service import RaceService
from app.infrastructure.persistence.race_repository import RaceRepository

R = "app.application.races.race_service"
M = "app.application.coach.memory.runner_memory_service"

TODAY = date(2026, 10, 17)

FIFTEEN = "2026-12-20"
HALF = "2027-04-04"

LONG = "Santander Track&Field Run Series - Villa-Lobos (15 km)"
HALF_NAME = "31ª Maratona Internacional de São Paulo 2027 — Meia Maratona (21 km)"


class _Profile:
    """Perfil em memória: guarda a âncora e registra cada escrita."""

    def __init__(self, race_date=FIFTEEN, target_race=LONG, target_time="1:15:00"):

        self.fields = {
            "race_date": race_date,
            "target_race": target_race,
            "target_time": target_time,
        }

        self.writes: list[dict] = []

    def load(self, _profile):

        return SimpleNamespace(**self.fields)

    def update_fields(self, _profile, updates):

        self.writes.append(dict(updates))

        self.fields.update(updates)


def _seed(profile="p", races=None):

    repo = RaceRepository()

    for name, when, target in races or [
        (LONG, FIFTEEN, "1:15:00"),
        (HALF_NAME, HALF, "1:59:59"),
    ]:

        repo.add(profile, name, when, target)


def _sync(fake, race, profile="p"):

    with (
        patch(f"{R}.today_local", return_value=TODAY),
        patch(f"{M}.RunnerProfileRepository", return_value=fake),
        patch(f"{R}.RunnerProfileRepository", return_value=fake),
        patch(f"{R}.RunnerMemoryService.process"),
    ):

        RunnerMemoryService._sync_race(profile, race)


def _dates(profile="p"):

    return sorted(r["date"] for r in RaceRepository().load(profile))


# ---- cancelamento -----------------------------------------------------------


def test_cancel_without_saying_which_removes_the_anchor_race():
    """'Cancelaram a prova' (sem dizer qual): sai a âncora (o 15 km) e o plano
    passa a mirar a meia."""

    _seed()

    fake = _Profile()

    _sync(fake, {"clear": True})

    assert _dates() == [HALF]
    assert fake.fields["race_date"] == HALF
    assert fake.fields["target_time"] == "1:59:59"


def test_cancel_by_name_removes_that_race_and_keeps_the_anchor():
    """'Não vou mais correr a meia': sai a meia; o 15 km segue como âncora (não
    é a âncora que foi limpa, como acontecia antes)."""

    _seed()

    fake = _Profile()

    _sync(fake, {"clear": True, "name": "meia maratona"})

    assert _dates() == [FIFTEEN]
    assert fake.fields["race_date"] == FIFTEEN


def test_cancel_by_date_and_by_month():

    _seed()

    _sync(_Profile(), {"clear": True, "date": HALF})

    assert _dates() == [FIFTEEN]

    # 'a de dezembro': sem o dia exato o extrator usa o dia 15 do mês
    _seed("q")

    _sync(_Profile(), {"clear": True, "date": "2026-12-15"}, profile="q")

    assert _dates("q") == [HALF]


def test_ambiguous_cancel_removes_nothing():
    """Duas provas de 15 km e 'cancelei a de 15 km': não adivinha qual."""

    _seed(races=[("Corrida A (15 km)", FIFTEEN, None), ("Corrida B (15 km)", HALF, None)])

    fake = _Profile()

    _sync(fake, {"clear": True, "name": "15 km"})

    assert _dates() == [FIFTEEN, HALF]


def test_cancelling_the_only_race_clears_the_plan_anchor():

    _seed(races=[(LONG, FIFTEEN, "1:15:00")])

    fake = _Profile()

    _sync(fake, {"clear": True})

    assert _dates() == []
    assert fake.fields["race_date"] is None
    assert fake.fields["target_race"] is None


def test_athlete_without_a_race_list_keeps_the_old_behaviour():
    """Nunca usou a lista e a âncora do perfil não estava nela: o 'clear'
    limpa a âncora como sempre."""

    fake = _Profile(race_date=None, target_race=None, target_time=None)

    # a âncora do perfil é importada pra lista na reconciliação (prova futura)
    fake.fields.update(race_date=FIFTEEN, target_race="15 km", target_time="1:15:00")

    _sync(fake, {"clear": True})

    assert _dates() == []
    assert fake.fields["race_date"] is None


def test_race_that_already_happened_is_not_removed_and_anchor_moves_on():
    """'Já aconteceu': a prova passada fica (histórico) e a âncora vai pra
    próxima futura — antes o 'clear' deixava o plano sem alvo com a meia ali."""

    _seed(races=[("10 km de Setembro", "2026-09-19", "00:57:00"), (HALF_NAME, HALF, "1:59:59")])

    fake = _Profile(race_date="2026-09-19", target_race="10 km de Setembro", target_time="00:57:00")

    _sync(fake, {"clear": True})

    assert _dates() == ["2026-09-19", HALF]
    assert fake.fields["race_date"] == HALF


# ---- remarcação -------------------------------------------------------------


def test_postponed_race_moves_instead_of_duplicating():
    """'Adiaram a prova de 20/12 pra 10/01': a MESMA prova muda de data."""

    _seed()

    fake = _Profile()

    _sync(
        fake,
        {"name": "Villa-Lobos", "date": "2027-01-10", "moved_from": FIFTEEN},
    )

    races = RaceRepository().load("p")

    assert sorted(r["date"] for r in races) == ["2027-01-10", HALF]

    moved = next(r for r in races if r["date"] == "2027-01-10")

    assert moved["name"] == LONG
    assert fake.fields["race_date"] == "2027-01-10"


def test_postponed_by_equivalent_name_without_the_old_date():

    _seed()

    _sync(_Profile(), {"name": "Villa-Lobos", "date": "2027-01-10"})

    assert _dates() == ["2027-01-10", HALF]


def test_distance_only_name_is_not_treated_as_a_postponement():
    """'15 km' em outra data pode ser OUTRA prova de 15 km: sem a data antiga e sem
    nome equivalente, entra como prova nova."""

    _seed()

    _sync(_Profile(), {"name": "15 km", "date": "2027-02-14"})

    assert _dates() == [FIFTEEN, "2027-02-14", HALF]


def test_mentioning_a_farther_race_does_not_steal_the_anchor():
    """O atleta cita a meia; o 15 km (mais perto) continua sendo a âncora."""

    _seed(races=[(LONG, FIFTEEN, "1:15:00")])

    fake = _Profile()

    _sync(fake, {"name": "Meia Maratona de SP", "date": HALF, "target_time": "1:59:59"})

    assert _dates() == [FIFTEEN, HALF]
    assert fake.fields["race_date"] == FIFTEEN
    assert fake.fields["target_time"] == "1:15:00"


# ---- extração: parse do que a IA devolve -------------------------------------


def test_parse_race_keeps_which_race_was_cleared():

    parse = MemoryExtractionEngine._parse_race

    assert parse({"clear": True}) == {"clear": True}

    assert parse({"clear": True, "name": " meia maratona ", "date": "2026-12-20"}) == {
        "clear": True, "name": "meia maratona", "date": "2026-12-20",
    }

    # data inválida é ignorada (não derruba nem chuta)
    assert parse({"clear": True, "date": "dezembro"}) == {"clear": True}


def test_parse_race_carries_a_valid_moved_from_only():

    parse = MemoryExtractionEngine._parse_race

    ok = parse({"name": "15 km", "date": "2027-01-10", "moved_from": "2026-12-20"})

    assert ok["moved_from"] == "2026-12-20"

    bad = parse({"name": "15 km", "date": "2027-01-10", "moved_from": "semana que vem"})

    assert "moved_from" not in bad


def test_race_service_direct_cancel_returns_what_was_removed():

    _seed()

    with patch(f"{R}.today_local", return_value=TODAY):

        removed = RaceService.cancel_from_conversation("p", name="meia")

    assert removed["date"] == HALF
    assert _dates() == [FIFTEEN]
