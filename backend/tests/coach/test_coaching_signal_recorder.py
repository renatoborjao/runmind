import asyncio
from unittest.mock import MagicMock, patch

from app.application.coach.conversation.proposal_flow import ProposalFlow
from app.application.coach.memory.coaching_signal_recorder import (
    CoachingSignalRecorder,
)
from app.core.clock import now_local
from app.domain.entities.plan_proposal import PlanProposal

PF = "app.application.coach.conversation.proposal_flow"


def _point_to_tmp(tmp_path, monkeypatch):

    monkeypatch.setattr(
        CoachingSignalRecorder,
        "_dir",
        staticmethod(lambda: tmp_path),
    )


def test_record_accumulates(tmp_path, monkeypatch):

    _point_to_tmp(tmp_path, monkeypatch)

    CoachingSignalRecorder.record("renato", "aceitou_move", "moveu terça")
    CoachingSignalRecorder.record("renato", "aceitou_aversion", "trocou tiro")

    signals = CoachingSignalRecorder.load("renato")

    assert len(signals) == 2
    assert signals[0]["kind"] == "aceitou_move"
    assert signals[1]["detail"] == "trocou tiro"
    assert "at" in signals[0]


def test_clear_empties(tmp_path, monkeypatch):

    _point_to_tmp(tmp_path, monkeypatch)

    CoachingSignalRecorder.record("renato", "aceitou_skip", "pulou quinta")

    CoachingSignalRecorder.clear("renato")

    assert CoachingSignalRecorder.load("renato") == []


def test_load_missing_profile_is_empty(tmp_path, monkeypatch):

    _point_to_tmp(tmp_path, monkeypatch)

    assert CoachingSignalRecorder.load("ninguem") == []


def test_cap_keeps_most_recent(tmp_path, monkeypatch):

    _point_to_tmp(tmp_path, monkeypatch)

    for i in range(60):

        CoachingSignalRecorder.record("renato", "aceitou_move", f"m{i}")

    signals = CoachingSignalRecorder.load("renato")

    assert len(signals) == 50
    # os mais recentes sobrevivem
    assert signals[-1]["detail"] == "m59"
    assert signals[0]["detail"] == "m10"


def _proposal() -> PlanProposal:

    return PlanProposal(
        kind="move",
        week_start="2026-07-06",
        preview="Movo seu longão pro sábado. Aplico?",
        created_at=now_local().isoformat(),
        operations=[{"action": "drop", "day": "Sunday"}],
    )


def test_accepting_a_proposal_records_source_a_signal(tmp_path, monkeypatch):
    """Chokepoint: aceitar uma correção grava o sinal da Fonte A."""

    _point_to_tmp(tmp_path, monkeypatch)

    repo = MagicMock()
    repo.load.return_value = _proposal()

    applier = MagicMock()
    applier.apply.return_value = "PLANO"

    with patch(f"{PF}.PlanProposalRepository", return_value=repo), patch(
        f"{PF}.PlanChangeApplier", applier
    ):

        asyncio.run(ProposalFlow.resolve("renato", MagicMock(), "pode aplicar"))

    signals = CoachingSignalRecorder.load("renato")

    assert len(signals) == 1
    assert signals[0]["kind"] == "aceitou_move"
    assert "longão" in signals[0]["detail"]


def test_recorder_failure_never_breaks_apply(tmp_path, monkeypatch):
    """Se registrar o sinal explodir, a proposta ainda é aplicada."""

    _point_to_tmp(tmp_path, monkeypatch)

    repo = MagicMock()
    repo.load.return_value = _proposal()

    applier = MagicMock()
    applier.apply.return_value = "PLANO"

    boom = MagicMock(side_effect=RuntimeError("disco cheio"))

    with patch(f"{PF}.PlanProposalRepository", return_value=repo), patch(
        f"{PF}.PlanChangeApplier", applier
    ), patch.object(CoachingSignalRecorder, "record", boom):

        reply = asyncio.run(
            ProposalFlow.resolve("renato", MagicMock(), "pode aplicar")
        )

    applier.apply.assert_called_once()
    assert "Ajustei" in reply
