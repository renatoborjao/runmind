from app.infrastructure.persistence import dispatch_guard as dg_module
from app.infrastructure.persistence.dispatch_guard import DispatchGuard


def test_mark_and_already_sent(tmp_path, monkeypatch):

    monkeypatch.setattr(dg_module, "_STORAGE", tmp_path / "dispatch")

    assert DispatchGuard.already_sent("briefing", "renato", "2026-07-14") is False

    DispatchGuard.mark("briefing", "renato", "2026-07-14")

    assert DispatchGuard.already_sent("briefing", "renato", "2026-07-14") is True

    # período diferente -> ainda não enviado
    assert DispatchGuard.already_sent("briefing", "renato", "2026-07-15") is False

    # outro atleta e outro kind são independentes
    assert DispatchGuard.already_sent("briefing", "camila", "2026-07-14") is False
    assert DispatchGuard.already_sent(
        "weekly_plan", "renato", "2026-07-14"
    ) is False
