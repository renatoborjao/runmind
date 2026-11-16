"""Fixtures globais: a lista de provas do atleta (`storage/races`) nunca toca o
disco real nos testes — o dossiê, o executor de meta e o onboarding passam a
registrar prova estruturada, e teste não pode sujar o storage de dev."""

import pytest

from app.infrastructure.persistence.processed_activity_guard import ProcessedActivityGuard
from app.infrastructure.persistence.race_repository import RaceRepository


@pytest.fixture(autouse=True)
def _isolated_race_storage(tmp_path, monkeypatch):

    def _init(self):

        self.storage = tmp_path / "races"

        self.storage.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(RaceRepository, "__init__", _init)


@pytest.fixture(autouse=True)
def _isolated_activity_guard(tmp_path, monkeypatch):
    """O guard de atividades já analisadas (e o teto de reanálise) escreve em `storage/`: no
    teste vai pra pasta temporária — teste nunca depende nem suja dado de atleta no disco."""

    def _init(self):

        self.storage = tmp_path / "guard"

        self.storage.mkdir(parents=True, exist_ok=True)

        self.file = self.storage / "processed_activities.json"

    monkeypatch.setattr(ProcessedActivityGuard, "__init__", _init)


@pytest.fixture(autouse=True)
def _conferente_without_athlete_storage(monkeypatch, request):
    """O conferente do plano (plan_check.facts_for) lê o dossiê do atleta no storage: nos testes da
    geração, ele recebe números vazios (os checks calam). Teste nunca lê dado de atleta. O teste do
    próprio conferente usa só as funções puras."""

    from app.application.coach.planning import plan_check

    monkeypatch.setattr(plan_check, "facts_for", lambda *a, **k: plan_check.CheckFacts())
