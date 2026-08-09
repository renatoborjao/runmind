"""Vigia da saúde do cérebro: alerta 1x quando a taxa de fallback estoura na
janela cheia e avisa quando normaliza. Storage e envio mockados (offline)."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.application.monitoring.coach_brain_monitor import (
    HIGH_RATE,
    WINDOW,
    CoachBrainMonitor,
)

MOD = "app.application.monitoring.coach_brain_monitor"


class _FakeRepo:
    """Repo em memória (sem tocar disco)."""

    def __init__(self):
        self.state = {"window": [], "alerted": False}

    def load(self):
        return dict(self.state)

    def save(self, state):
        self.state = dict(state)


def _run(outcomes, repo):
    """Roda record() pra cada desfecho; devolve as mensagens alertadas."""

    sent = []

    with (
        patch(f"{MOD}.CoachBrainHealthRepository", return_value=repo),
        patch(
            f"{MOD}.CoachBrainMonitor._notify",
            new=AsyncMock(side_effect=lambda m: sent.append(m)),
        ),
    ):

        for fb in outcomes:
            asyncio.run(CoachBrainMonitor.record(fallback=fb))

    return sent


def test_no_alert_below_min_sample():
    """Poucas mensagens (janela não cheia) nunca alerta, mesmo 100% fallback."""

    repo = _FakeRepo()

    sent = _run([True] * (WINDOW - 1), repo)

    assert sent == []
    assert repo.state["alerted"] is False


def test_alerts_once_when_fallback_rate_spikes():
    """Janela cheia com taxa acima do limiar => 1 alerta (e só 1)."""

    repo = _FakeRepo()

    # janela cheia toda em fallback = 100% > HIGH_RATE
    sent = _run([True] * (WINDOW + 5), repo)

    assert len(sent) == 1
    assert "fallback" in sent[0].lower()
    assert repo.state["alerted"] is True


def test_healthy_window_never_alerts():
    """Cérebro saudável (sempre respondeu) nunca alerta."""

    repo = _FakeRepo()

    sent = _run([False] * (WINDOW + 5), repo)

    assert sent == []
    assert repo.state["alerted"] is False


def test_recovery_notice_after_normalizing():
    """Depois de alertar, quando a taxa cai, avisa que normalizou (1x)."""

    repo = _FakeRepo()

    # 1) estoura (100% fallback, janela cheia) -> alerta
    _run([True] * WINDOW, repo)

    assert repo.state["alerted"] is True

    # 2) enche de sucessos -> taxa cai abaixo de LOW_RATE -> recuperação
    sent = _run([False] * WINDOW, repo)

    assert any("normalizou" in m.lower() for m in sent)
    assert repo.state["alerted"] is False


def test_high_rate_constant_is_sane():

    assert 0 < HIGH_RATE < 1
