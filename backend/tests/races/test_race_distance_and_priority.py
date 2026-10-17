from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.application.races.race_service import RaceService
from app.domain.value_objects.race_distance import parse_race_distance
from app.infrastructure.persistence.race_repository import RaceRepository

MOD = "app.application.races.race_service"

NEAR = "2027-11-01"
MID = "2028-03-01"
FAR = "2030-05-01"
PAST = "2020-01-01"


class _FakeProfile:

    def __init__(self):
        self.fields = {"race_date": None, "target_race": None, "target_time": None}

    def load(self, _profile):
        return SimpleNamespace(
            race_date=self.fields.get("race_date"),
            target_race=self.fields.get("target_race"),
            target_time=self.fields.get("target_time"),
        )

    def update_fields(self, _profile, updates):
        self.fields.update(updates)


def _ctx(tmp_path, fake):
    def repo_factory():
        r = RaceRepository()
        r.storage = tmp_path
        return r

    return (
        patch(f"{MOD}.RaceRepository", repo_factory),
        patch(f"{MOD}.RunnerProfileRepository", lambda: fake),
        patch(f"{MOD}.RunnerMemoryService.process"),
    )


# ---- distância pelo nome ----------------------------------------------------


@pytest.mark.parametrize("name,expected", [
    # nomes REAIS do renato2 e do mauricio
    ("Santander Track&Field Run Series - Villa-Lobos (15 km)", 15.0),
    ("31ª Maratona Internacional de São Paulo 2027 — Meia Maratona (21 km)", 21.0975),
    ("10 km", 10.0),
    ("15 km", 15.0),
    # armadilhas
    ("Maratona de São Paulo 2027", 42.195),          # o ano não vira distância
    ("Corrida da Cidade 2027 5k", 5.0),
    ("Volta da Pampulha 18km", 18.0),
    ("Meia de Floripa", 21.0975),
    ("Prova 21,1 km", 21.1),
    ("Corrida do Bairro", None),
    ("31ª Corrida", None),                            # número solto não é km
    ("", None),
    (None, None),
])
def test_parse_race_distance(name, expected):

    assert parse_race_distance(name) == expected


# ---- registro: distância e papel -------------------------------------------


def test_add_stores_distance_from_name_and_explicit_priority(tmp_path):
    fake = _FakeProfile()
    p1, p2, p3 = _ctx(tmp_path, fake)
    with p1, p2, p3 as memory:
        rec = RaceService.add("p", "Corrida (10 km)", NEAR, priority="B")

        assert rec["distance_km"] == 10.0
        assert rec["priority"] == "B"

        # o coach recebe o papel na memória
        sent = memory.call_args[0][1]["add"][0]["content"]
        assert "preparatória (B)" in sent


def test_explicit_distance_wins_over_the_name(tmp_path):
    fake = _FakeProfile()
    p1, p2, p3 = _ctx(tmp_path, fake)
    with p1, p2, p3:
        rec = RaceService.add("p", "Trail do Vale (10 km)", NEAR, distance_km=12.4)

        assert rec["distance_km"] == 12.4


def test_update_sets_priority_and_validates(tmp_path):
    fake = _FakeProfile()
    p1, p2, p3 = _ctx(tmp_path, fake)
    with p1, p2, p3:
        rec = RaceService.add("p", "Corrida (10 km)", NEAR)

        out = RaceService.update("p", rec["id"], priority="C")
        assert out["priority"] == "C"

        with pytest.raises(ValueError):
            RaceService.update("p", rec["id"], priority="Z")

        assert RaceService.update("p", "naoexiste", priority="A") is None

        # mudar o papel não mexe na âncora do perfil
        assert fake.fields["race_date"] == NEAR


# ---- sugestão de papel (os dois casos reais) --------------------------------


def test_single_future_race_is_suggested_as_main(tmp_path):
    """Mauricio: 10 km já passou, o 15 km é a única à frente → A."""

    fake = _FakeProfile()
    p1, p2, p3 = _ctx(tmp_path, fake)
    with p1, p2, p3:
        RaceService.add("p", "10 km", PAST, "00:57:00")
        RaceService.add("p", "15 km", NEAR, "01:22:30")

        by_name = {r["name"]: r for r in RaceService.list("p")}

        assert by_name["15 km"]["priority_suggested"] == "A"
        assert by_name["15 km"]["priority_effective"] == "A"
        # prova passada não recebe sugestão
        assert by_name["10 km"]["priority_suggested"] is None


def test_longest_future_race_is_suggested_main_and_the_other_preparatory(tmp_path):
    """Renato: 15 km (dez) + meia (abr) → meia A, 15 km B."""

    fake = _FakeProfile()
    p1, p2, p3 = _ctx(tmp_path, fake)
    with p1, p2, p3:
        RaceService.add("p", "Villa-Lobos (15 km)", NEAR, "1:15:00")
        RaceService.add("p", "Maratona SP — Meia Maratona (21 km)", MID, "1:59:59")

        by_name = {r["name"]: r for r in RaceService.list("p")}

        assert by_name["Maratona SP — Meia Maratona (21 km)"]["priority_effective"] == "A"
        assert by_name["Villa-Lobos (15 km)"]["priority_effective"] == "B"

        # a âncora do plano NÃO mudou: segue a prova mais próxima
        assert fake.fields["target_race"] == "Villa-Lobos (15 km)"


def test_athlete_choice_beats_the_suggestion(tmp_path):
    fake = _FakeProfile()
    p1, p2, p3 = _ctx(tmp_path, fake)
    with p1, p2, p3:
        a = RaceService.add("p", "Corrida (10 km)", NEAR)
        RaceService.add("p", "Maratona", FAR)

        RaceService.update("p", a["id"], priority="A")

        by_name = {r["name"]: r for r in RaceService.list("p")}

        assert by_name["Corrida (10 km)"]["priority_effective"] == "A"
        assert by_name["Corrida (10 km)"]["priority_suggested"] == "B"


def test_no_suggestion_when_distances_are_unknown(tmp_path):
    fake = _FakeProfile()
    p1, p2, p3 = _ctx(tmp_path, fake)
    with p1, p2, p3:
        RaceService.add("p", "Corrida do Bairro", NEAR)
        RaceService.add("p", "Corrida da Praça", FAR)

        assert all(
            r["priority_effective"] is None for r in RaceService.list("p")
        )


def test_legacy_race_without_distance_gets_it_from_the_name_on_read(tmp_path):
    """Prova gravada antes do campo existir: a leitura completa (sem regravar)."""

    fake = _FakeProfile()
    p1, p2, p3 = _ctx(tmp_path, fake)
    with p1, p2, p3:
        repo = RaceRepository()
        repo.storage = tmp_path
        repo.save("p", [{
            "id": "x1", "name": "Villa-Lobos (15 km)", "date": NEAR,
            "target_time": "1:15:00", "created_at": "2026-09-14T21:17:46-03:00",
        }])

        race = RaceService.list("p")[0]

        assert race["distance_km"] == 15.0
        assert race["distance_inferred"] is True
        assert race["priority"] is None                  # forma estável da API
        assert "distance_km" not in repo.load("p")[0]   # leitura não grava
