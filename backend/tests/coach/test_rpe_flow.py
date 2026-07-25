from datetime import timedelta

from app.application.coach.conversation.rpe_flow import RpeFlow
from app.core.clock import today_local
from app.infrastructure.persistence.session_rpe_repository import (
    SessionRpeRepository,
)


def _repo(tmp_path):

    repo = SessionRpeRepository()

    repo.storage = tmp_path

    return repo


def _patch_repo(monkeypatch, repo):
    """RpeFlow instancia o repo internamente; aponta pro tmp."""

    monkeypatch.setattr(
        "app.application.coach.conversation.rpe_flow.SessionRpeRepository",
        lambda: repo,
    )


# ---------------- _parse_rpe (disambiguação) ----------------


def test_parse_bare_number():

    assert RpeFlow._parse_rpe("7") == 7
    assert RpeFlow._parse_rpe("  8 ") == 8


def test_parse_labeled_and_out_of_ten():

    assert RpeFlow._parse_rpe("foi 8") == 8
    assert RpeFlow._parse_rpe("rpe 9") == 9
    assert RpeFlow._parse_rpe("uns 6") == 6
    assert RpeFlow._parse_rpe("7/10") == 7
    assert RpeFlow._parse_rpe("8 de 10") == 8


def test_parse_rejects_distances_and_pace():
    """Não confunde métrica de treino com RPE."""

    assert RpeFlow._parse_rpe("corri 8km") is None
    assert RpeFlow._parse_rpe("pace 5:30") is None
    assert RpeFlow._parse_rpe("foram 45 min") is None


def test_parse_out_of_range_is_none():

    assert RpeFlow._parse_rpe("15") is None


# ---------------- resolve (loop de captura) ----------------


def test_no_pending_returns_none(tmp_path, monkeypatch):

    _patch_repo(monkeypatch, _repo(tmp_path))

    assert RpeFlow.resolve("renato", "7") is None


def test_resolves_and_records_srpe(tmp_path, monkeypatch):

    repo = _repo(tmp_path)

    _patch_repo(monkeypatch, repo)

    repo.set_pending(
        "renato", activity_id=99, day=today_local().isoformat(),
        duration_min=60.0,
    )

    reply = RpeFlow.resolve("renato", "foi 8")

    assert reply is not None and "RPE 8" in reply

    sessions = repo.load_sessions("renato")

    assert len(sessions) == 1
    assert sessions[0].rpe == 8
    assert sessions[0].srpe == 480.0        # 60 min × 8
    assert repo.get_pending("renato") is None   # pendente limpo


def test_non_number_reply_does_not_capture(tmp_path, monkeypatch):
    """Com pendente, uma resposta que não é número segue a conversa normal."""

    repo = _repo(tmp_path)

    _patch_repo(monkeypatch, repo)

    repo.set_pending(
        "renato", activity_id=99, day=today_local().isoformat(),
        duration_min=60.0,
    )

    assert RpeFlow.resolve("renato", "foi muito bom, valeu!") is None
    assert repo.get_pending("renato") is not None   # segue esperando


def test_stale_pending_is_dropped(tmp_path, monkeypatch):
    """Treino de 3 dias atrás: não captura número solto como RPE dele."""

    repo = _repo(tmp_path)

    _patch_repo(monkeypatch, repo)

    old_day = (today_local() - timedelta(days=3)).isoformat()

    repo.set_pending(
        "renato", activity_id=99, day=old_day, duration_min=60.0,
    )

    assert RpeFlow.resolve("renato", "8") is None
    assert repo.get_pending("renato") is None       # pendente velho descartado


# ---------------- recent_note (uso na dose) ----------------


def test_recent_high_rpe_becomes_dose_note(tmp_path, monkeypatch):

    repo = _repo(tmp_path)

    _patch_repo(monkeypatch, repo)

    repo.set_pending(
        "renato", activity_id=1, day=today_local().isoformat(),
        duration_min=50.0,
    )

    RpeFlow.resolve("renato", "9")

    note = RpeFlow.recent_note("renato")

    assert "muito puxado" in note
    assert "RPE 9" in note


def test_moderate_rpe_no_dose_note(tmp_path, monkeypatch):

    repo = _repo(tmp_path)

    _patch_repo(monkeypatch, repo)

    repo.set_pending(
        "renato", activity_id=1, day=today_local().isoformat(),
        duration_min=50.0,
    )

    RpeFlow.resolve("renato", "5")

    assert RpeFlow.recent_note("renato") == ""
