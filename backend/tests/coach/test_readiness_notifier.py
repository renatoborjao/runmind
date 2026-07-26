import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.review.readiness_notifier import ReadinessNotifier
from app.domain.entities.readiness_diary_entry import ReadinessDiaryEntry
from app.domain.entities.readiness_verdict import (
    READINESS_BRAKE,
    READINESS_CAUTION,
    READINESS_GREEN,
    ReadinessVerdict,
)

MOD = "app.application.review.readiness_notifier"


def _verdict(tier, limiter="sono") -> ReadinessVerdict:

    return ReadinessVerdict(
        tier=tier, reason="motivo", should_speak=True,
        body_state="RECOVERY_FLAG", limiter=limiter,
    )


def _entry(tier, would_notify=True) -> ReadinessDiaryEntry:

    return ReadinessDiaryEntry(
        day="2026-07-28", at="2026-07-28T09:00:00-03:00", tier=tier,
        body_state="RECOVERY_FLAG", reason="motivo", demand="demanding",
        would_notify=would_notify, from_tier="NEUTRAL",
    )


def _run(tier, *, flag, would_notify=True, already_sent=False):
    """Roda observe_and_maybe_alert com tudo mockado. Devolve (send_mock,
    mark_mock)."""

    send = AsyncMock()

    with (
        patch(f"{MOD}.ReadinessService") as svc,
        patch(f"{MOD}.get_settings",
              return_value=SimpleNamespace(readiness_alerts_enabled=flag)),
        patch(f"{MOD}.CoachOutbox") as outbox,
        patch(f"{MOD}.DispatchGuard") as guard,
    ):

        svc.evaluate = AsyncMock(
            return_value=(_verdict(tier), _entry(tier, would_notify))
        )
        outbox.send = send
        guard.already_sent.return_value = already_sent  # mark é sync (auto-mock)

        asyncio.run(
            ReadinessNotifier.observe_and_maybe_alert(
                "renato2", SimpleNamespace()
            )
        )

        # observação SEMPRE roda
        svc.evaluate.assert_awaited_once()

        return send, guard


def test_flag_desligada_so_observa_nunca_envia():

    send, _ = _run(READINESS_CAUTION, flag=False)

    send.assert_not_awaited()


def test_flag_ligada_envia_caution():

    send, guard = _run(READINESS_CAUTION, flag=True)

    send.assert_awaited_once()
    guard.mark.assert_called_once()


def test_flag_ligada_envia_green():

    send, _ = _run(READINESS_GREEN, flag=True)

    send.assert_awaited_once()


def test_brake_nao_duplica_fica_com_o_proposer():

    # STRAINED/BRAKE é tratado pelo BodyConductNotifier — o vigia não manda
    send, _ = _run(READINESS_BRAKE, flag=True)

    send.assert_not_awaited()


def test_sem_virada_nao_envia():

    send, _ = _run(READINESS_CAUTION, flag=True, would_notify=False)

    send.assert_not_awaited()


def test_dedup_no_mesmo_dia_e_estado():

    send, _ = _run(READINESS_CAUTION, flag=True, already_sent=True)

    send.assert_not_awaited()
