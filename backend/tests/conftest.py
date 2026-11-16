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


@pytest.fixture(autouse=True)
def _isolated_shared_storage(tmp_path, monkeypatch):
    """Os repositórios que montam o caminho de `backend/storage` sozinhos e que os testes tocavam
    sem querer (16/11: 6 pastas apareciam no PC depois da suíte). Aqui vão pra uma pasta temporária.
    A trava do fim da sessão (pytest_sessionfinish) pega qualquer um novo."""

    from app.application.coach.memory import coaching_signal_recorder
    from app.infrastructure.persistence import (
        ai_health_repository,
        app_notification_repository,
        coach_brain_health_repository,
        coach_brain_log_repository,
        frequency_offer_store,
    )

    root = tmp_path / "storage"

    monkeypatch.setattr(ai_health_repository, "_STORAGE", root)
    monkeypatch.setattr(coach_brain_health_repository, "_STORAGE", root)
    monkeypatch.setattr(frequency_offer_store, "_STORAGE", root / "reconcile" / "freq_offer")

    signals = root / "learning_signals"

    def _signals_dir():

        signals.mkdir(parents=True, exist_ok=True)

        return signals

    monkeypatch.setattr(
        coaching_signal_recorder.CoachingSignalRecorder, "_dir", staticmethod(_signals_dir),
    )

    for module, cls_name, sub in (
        (app_notification_repository, "AppNotificationRepository", "app_notifications"),
        (coach_brain_log_repository, "CoachBrainLogRepository", "coach_brain_log"),
    ):

        cls = getattr(module, cls_name)

        original = cls.__init__

        def _init(self, *a, _original=original, _sub=sub, **k):

            _original(self, *a, **k)

            self.storage = root / _sub

            self.storage.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(cls, "__init__", _init)


_STORAGE_DIR = __import__("pathlib").Path(__file__).resolve().parents[1] / "storage"

_STORAGE_EXISTED = _STORAGE_DIR.exists()


def pytest_sessionfinish(session, exitstatus):
    """TRAVA: teste nunca escreve dado no storage do repositório. Se a suíte criou
    `backend/storage`, ela falha (e o deploy não sobe) dizendo o que apareceu."""

    if _STORAGE_EXISTED or not _STORAGE_DIR.exists():

        return

    created = sorted(str(p.relative_to(_STORAGE_DIR)) for p in _STORAGE_DIR.rglob("*") if p.is_file())

    if not created:

        # só pastas vazias (repositórios criam o diretório ao iniciar): nada de dado — some com elas
        import shutil

        shutil.rmtree(_STORAGE_DIR, ignore_errors=True)

        return

    print(f"\nTRAVA: teste escreveu no storage real (backend/storage): {created[:10]}")

    session.exitstatus = 1
