from types import SimpleNamespace
from unittest.mock import patch

from app.application.races.race_service import RaceService
from app.infrastructure.persistence.race_repository import RaceRepository

MOD = "app.application.races.race_service"

# datas confortavelmente no futuro (hoje do projeto ~2026) — evita flakiness
NEAR = "2027-11-01"
FAR = "2030-05-01"
PAST = "2020-01-01"


class _FakeProfile:
    """Perfil em memória: guarda os campos-âncora que o RaceService escreve."""

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


def test_nearest_future_race_anchors_profile(tmp_path):
    fake = _FakeProfile()
    p1, p2, p3 = _ctx(tmp_path, fake)
    with p1, p2, p3:
        RaceService.add("p", "Maratona", FAR, "3:30:00")
        RaceService.add("p", "10k", NEAR, "0:50:00")

        # a prova futura MAIS PRÓXIMA vira a âncora do perfil
        assert fake.fields["race_date"] == NEAR
        assert fake.fields["target_race"] == "10k"
        assert fake.fields["target_time"] == "0:50:00"

        races = RaceService.list("p")
        anchors = [r for r in races if r["is_anchor"]]
        assert len(anchors) == 1 and anchors[0]["name"] == "10k"
        # ordenada por data
        assert [r["name"] for r in races] == ["10k", "Maratona"]


def test_removing_anchor_resyncs_to_next(tmp_path):
    fake = _FakeProfile()
    p1, p2, p3 = _ctx(tmp_path, fake)
    with p1, p2, p3:
        RaceService.add("p", "Maratona", FAR)
        near = RaceService.add("p", "10k", NEAR)

        assert fake.fields["target_race"] == "10k"

        RaceService.remove("p", near["id"])

        # âncora passa pra próxima futura
        assert fake.fields["race_date"] == FAR
        assert fake.fields["target_race"] == "Maratona"


def test_past_race_does_not_anchor(tmp_path):
    fake = _FakeProfile()
    p1, p2, p3 = _ctx(tmp_path, fake)
    with p1, p2, p3:
        RaceService.add("p", "Prova velha", PAST)

        # nenhuma prova futura → âncora limpa
        assert fake.fields["race_date"] is None
        assert fake.fields["target_race"] is None

        races = RaceService.list("p")
        assert races[0]["past"] is True
        assert races[0]["is_anchor"] is False


def test_coach_set_race_is_reconciled_into_list(tmp_path):
    fake = _FakeProfile()
    # coach cadastrou por conversa (só o perfil sabe, repo vazio)
    fake.fields = {"race_date": NEAR, "target_race": "Meia do coach", "target_time": "1:50:00"}
    p1, p2, p3 = _ctx(tmp_path, fake)
    with p1, p2, p3:
        races = RaceService.list("p")

        assert len(races) == 1
        assert races[0]["name"] == "Meia do coach"
        assert races[0]["is_anchor"] is True
