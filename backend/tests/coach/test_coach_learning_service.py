from datetime import datetime, timedelta

from app.application.coach.memory.coach_learning_service import (
    CoachLearningService,
    LEARNING_TTL_WEEKS,
)
from app.core.clock import now_local
from app.domain.entities.coach_learning import CoachLearning
from app.infrastructure.persistence.coach_learning_repository import (
    CoachLearningRepository,
)


def _service_repo(tmp_path, monkeypatch):
    """Aponta o repositório pra um storage temporário e devolve o repo."""

    repo = CoachLearningRepository()

    repo.storage = tmp_path

    monkeypatch.setattr(
        "app.application.coach.memory.coach_learning_service"
        ".CoachLearningRepository",
        lambda: repo,
    )

    return repo


def _seed(repo, profile, expires_at, entry_id="cl-old", evidence=1):

    repo.add(
        profile,
        CoachLearning(
            id=entry_id,
            category="aderencia",
            content="Cumpre tiro de 800m sempre",
            source="weekly_distillation",
            created_at=now_local().isoformat(),
            expires_at=expires_at,
            evidence_count=evidence,
        ),
    )


def test_process_adds_learning_with_ttl(tmp_path, monkeypatch):

    repo = _service_repo(tmp_path, monkeypatch)

    CoachLearningService.process(
        "renato",
        {"add": [{"category": "limite", "content": "Ponto ótimo é 3 dias"}]},
        level="Intermediate",
        goal_kind="race",
    )

    stored = repo.load("renato")

    assert len(stored) == 1

    entry = stored[0]

    assert entry.category == "limite"
    assert entry.level == "Intermediate"
    assert entry.goal_kind == "race"
    assert entry.evidence_count == 1

    # validade ~8 semanas à frente
    expires = datetime.fromisoformat(entry.expires_at)

    expected = now_local() + timedelta(weeks=LEARNING_TTL_WEEKS)

    assert abs((expires - expected).total_seconds()) < 60


def test_process_reconfirm_bumps_expiry_and_evidence(tmp_path, monkeypatch):

    repo = _service_repo(tmp_path, monkeypatch)

    old_expiry = (now_local() + timedelta(days=1)).isoformat()

    _seed(repo, "renato", old_expiry, entry_id="cl-1", evidence=2)

    CoachLearningService.process(
        "renato",
        {"reconfirm": ["cl-1"]},
    )

    entry = repo.load("renato")[0]

    assert entry.evidence_count == 3

    # validade foi empurrada bem além do +1 dia original
    assert datetime.fromisoformat(entry.expires_at) > now_local() + timedelta(
        weeks=LEARNING_TTL_WEEKS - 1
    )


def test_process_archives(tmp_path, monkeypatch):

    repo = _service_repo(tmp_path, monkeypatch)

    _seed(
        repo,
        "renato",
        (now_local() + timedelta(weeks=4)).isoformat(),
        entry_id="cl-1",
    )

    CoachLearningService.process("renato", {"archive": ["cl-1"]})

    assert repo.active("renato") == []
    # continua no disco pro histórico/debug
    assert len(repo.load("renato")) == 1


def test_render_only_returns_active_non_expired(tmp_path, monkeypatch):

    repo = _service_repo(tmp_path, monkeypatch)

    _seed(
        repo,
        "renato",
        (now_local() + timedelta(weeks=4)).isoformat(),
        entry_id="cl-live",
    )

    # já vencido: não deve aparecer no render
    _seed(
        repo,
        "renato",
        (now_local() - timedelta(days=1)).isoformat(),
        entry_id="cl-expired",
    )

    rendered = CoachLearningService.render("renato")

    assert "Cumpre tiro de 800m sempre" in rendered
    assert "observando ELE" in rendered
    # só um item vivo — a linha de item aparece uma vez
    assert rendered.count("[aderencia]") == 1


def test_render_empty_when_nothing(tmp_path, monkeypatch):

    _service_repo(tmp_path, monkeypatch)

    assert CoachLearningService.render("ninguem") == ""
