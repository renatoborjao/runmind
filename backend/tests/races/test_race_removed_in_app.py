"""Remover a prova PELO APP (botão × da tela de provas): sem prova zumbi e sem a
memória do coach ainda falando da prova apagada. Caso real: renato2 e mauricio."""

from types import SimpleNamespace
from unittest.mock import patch

from app.application.races.race_service import RaceService
from app.infrastructure.persistence.race_repository import RaceRepository

R = "app.application.races.race_service"
MEM_REPO = "app.infrastructure.persistence.runner_memory_repository.RunnerMemoryRepository"

NEAR = "2027-11-01"
FAR = "2030-05-01"


class _Profile:

    def __init__(self):

        self.fields = {"race_date": None, "target_race": None, "target_time": None}

    def load(self, _profile):

        return SimpleNamespace(**self.fields)

    def update_fields(self, _profile, updates):

        self.fields.update(updates)


class _Memory:
    """Memória do coach em memória: lista de entradas ativas e o que foi arquivado."""

    def __init__(self, entries):

        self.entries = [
            SimpleNamespace(id=f"m{i}", category=cat, content=text)
            for i, (cat, text) in enumerate(entries)
        ]

        self.archived: list[str] = []

    def active(self, _profile):

        return [e for e in self.entries if e.id not in self.archived]

    def archive(self, _profile, ids):

        self.archived.extend(ids)


def _ctx(fake_profile, memory=None):

    return (
        patch(f"{R}.RunnerProfileRepository", lambda: fake_profile),
        patch(f"{R}.RunnerMemoryService.process"),
        patch(MEM_REPO, lambda: memory or _Memory([])),
    )


def test_deleting_the_last_race_does_not_bring_it_back():
    """Antes: a lista esvaziava mas a âncora do perfil ficava; na leitura seguinte a
    prova apagada era REIMPORTADA do perfil (prova zumbi)."""

    fake = _Profile()

    p1, p2, p3 = _ctx(fake)

    with p1, p2, p3:

        race = RaceService.add("p", "10 km", NEAR, "0:50:00")

        assert fake.fields["race_date"] == NEAR

        assert RaceService.remove("p", race["id"]) is True

        # o perfil volta ao treino de base...
        assert fake.fields["race_date"] is None
        assert fake.fields["target_race"] is None

        # ...e a prova NÃO volta pela reconciliação da leitura
        assert RaceService.list("p") == []


def test_deleting_one_of_two_keeps_the_other_as_anchor():

    fake = _Profile()

    p1, p2, p3 = _ctx(fake)

    with p1, p2, p3:

        RaceService.add("p", "Maratona", FAR)
        near = RaceService.add("p", "10 km", NEAR)

        RaceService.remove("p", near["id"])

        assert fake.fields["race_date"] == FAR
        assert [r["name"] for r in RaceService.list("p")] == ["Maratona"]


def test_deleting_a_race_forgets_what_the_coach_memory_said_about_it():
    """A memória 'Prova cadastrada pelo app: 10 km em 2027-11-01' não pode seguir
    ativa depois que o atleta apagou a prova."""

    fake = _Profile()

    memory = _Memory([
        ("objetivo", f"Prova cadastrada pelo app: 10 km em {NEAR} (alvo 0:50:00)"),
        ("objetivo", f"Prova: Meia, 21 km, em {FAR}, tempo-alvo 1:59:59"),
        ("objetivo", "Quer correr pela saúde, sem pressa"),
        ("lesao", f"Dor no joelho desde {NEAR}"),
    ])

    p1, p2, p3 = _ctx(fake, memory)

    with p1, p2, p3:

        RaceService.add("p", "10 km", NEAR, "0:50:00")
        race = RaceService.add("p", "Meia", FAR)

        RaceService.remove("p", race["id"])

    # só a memória DA prova apagada (a meia) sai; a da 10 km, o objetivo geral e a
    # lesão ficam
    assert [e.content[:22] for e in memory.entries if e.id in memory.archived] == [
        "Prova: Meia, 21 km, em",
    ]


def test_cancelled_by_conversation_also_forgets_the_memory():

    fake = _Profile()

    memory = _Memory([("objetivo", f"Prova: 15 km, em {NEAR}, tempo-alvo 1:15:00")])

    p1, p2, p3 = _ctx(fake, memory)

    with p1, p2, p3:

        RaceRepository().add("p", "15 km", NEAR, "1:15:00")

        removed = RaceService.cancel_from_conversation("p", name="15 km")

    assert removed is not None and len(memory.archived) == 1


def test_memory_written_with_the_month_name_is_forgotten_too():
    """Memórias escritas pela extração ('em 20 de dezembro de 2026') também saem."""

    fake = _Profile()

    memory = _Memory([
        ("objetivo", "Inscrito na prova de 15km da Track&Field em 20 de dezembro de 2026"),
        ("objetivo", "Meta de pace abaixo de 5:30 min/km para a prova de 15km"),
    ])

    p1, p2, p3 = _ctx(fake, memory)

    with p1, p2, p3:

        race = RaceService.add("p", "15 km", "2026-12-20")
        RaceService.add("p", "Meia", FAR)
        RaceService.remove("p", race["id"])

    assert len(memory.archived) == 1
    assert "Inscrito na prova" in next(
        e.content for e in memory.entries if e.id in memory.archived
    )


def test_strategy_memory_that_mentions_both_races_is_kept():
    """'Meia como norte, 15k (20/12/2026) como degrau' fala das DUAS: apagar uma não
    pode levar junto o que vale pra outra (caso real do renato2)."""

    fake = _Profile()

    strategy = (
        "ESTRATEGIA (27/09): o NORTE é a MEIA em 04/04/2027; a 15k (20/12/2026) é o "
        "degrau"
    )

    memory = _Memory([
        ("objetivo", strategy),
        ("objetivo", "Prova: Villa-Lobos, 15 km, em 2026-12-20, tempo-alvo 1:15:00"),
    ])

    p1, p2, p3 = _ctx(fake, memory)

    with p1, p2, p3:

        race = RaceService.add("p", "Villa-Lobos (15 km)", "2026-12-20")
        RaceService.add("p", "Meia (21 km)", "2027-04-04")
        RaceService.remove("p", race["id"])

    forgotten = [e.content for e in memory.entries if e.id in memory.archived]

    assert forgotten == ["Prova: Villa-Lobos, 15 km, em 2026-12-20, tempo-alvo 1:15:00"]
