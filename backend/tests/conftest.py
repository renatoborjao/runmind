"""Fixtures globais: a lista de provas do atleta (`storage/races`) nunca toca o
disco real nos testes — o dossiê, o executor de meta e o onboarding passam a
registrar prova estruturada, e teste não pode sujar o storage de dev."""

import pytest

from app.infrastructure.persistence.race_repository import RaceRepository


@pytest.fixture(autouse=True)
def _isolated_race_storage(tmp_path, monkeypatch):

    def _init(self):

        self.storage = tmp_path / "races"

        self.storage.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(RaceRepository, "__init__", _init)
