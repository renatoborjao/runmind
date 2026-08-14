import asyncio
from datetime import date
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


def _verdict(tier, signals=()) -> ReadinessVerdict:

    return ReadinessVerdict(
        tier=tier, reason="motivo", should_speak=True,
        body_state="RECOVERY_FLAG", limiter="sono", signals=signals,
    )


def _entry(tier, would_notify=True) -> ReadinessDiaryEntry:

    return ReadinessDiaryEntry(
        day="2026-07-28", at="2026-07-28T06:00:00-03:00", tier=tier,
        body_state="RECOVERY_FLAG", reason="motivo", demand="demanding",
        would_notify=would_notify, from_tier="NEUTRAL",
    )


def _block(tier, *, flag, would_notify=True, illness=None, already_sent=False):
    """Roda block() com tudo mockado; devolve a mensagem (ou None)."""

    with (
        patch(f"{MOD}.ReadinessService") as svc,
        patch(f"{MOD}.get_settings",
              return_value=SimpleNamespace(readiness_alerts_enabled=flag)),
        patch(f"{MOD}.CheckinRepository") as repo_cls,
        patch(f"{MOD}.DispatchGuard") as guard,
        patch(f"{MOD}.today_local", return_value=date(2026, 8, 14)),
    ):

        svc.evaluate = AsyncMock(
            return_value=(_verdict(tier), _entry(tier, would_notify))
        )

        repo_cls.return_value.recent_illness.return_value = illness

        guard.already_sent.return_value = already_sent

        result = asyncio.run(ReadinessNotifier.block("renato2"))

        # observação SEMPRE roda (grava o diário — o gate do Renato)
        svc.evaluate.assert_awaited_once()

        return result


def test_flag_desligada_so_observa_nao_fala():

    assert _block(READINESS_CAUTION, flag=False) is None


def test_flag_ligada_narra_caution():

    assert _block(READINESS_CAUTION, flag=True) is not None


def test_flag_ligada_narra_green():

    assert _block(READINESS_GREEN, flag=True) is not None


def test_brake_fica_com_o_proposer():

    # STRAINED/BRAKE é tratado pelo BodyConductNotifier — o bloco não fala
    assert _block(READINESS_BRAKE, flag=True) is None


def test_sem_virada_nao_fala():

    assert _block(READINESS_CAUTION, flag=True, would_notify=False) is None


def test_message_caution_narra_os_sinais():

    v = ReadinessVerdict(
        tier=READINESS_CAUTION, reason="x", should_speak=True,
        body_state="RECOVERY_FLAG", limiter="sono",
        signals=("você teve 2 noites curtas essa semana", "seu HRV vem caindo"),
    )

    msg = ReadinessNotifier._message(v)

    assert "2 noites curtas" in msg
    assert "seu HRV vem caindo" in msg
    assert "pegar leve" in msg


def test_message_caution_sem_sinais_ainda_humano():

    v = ReadinessVerdict(
        tier=READINESS_CAUTION, reason="x", should_speak=True,
        body_state="RECOVERY_FLAG", limiter=None, signals=(),
    )

    msg = ReadinessNotifier._message(v)

    assert "recuperação" in msg.lower()


def test_doenca_suprime_puxar_e_manda_cuidado():
    """O bug real: atleta gripado + corpo verde no relógio -> NÃO manda puxar;
    manda mensagem de descanso/cuidado. A doença manda sobre o HRV."""

    ill = SimpleNamespace(day="2026-08-13")

    msg = _block(READINESS_GREEN, flag=True, illness=ill)

    assert msg is not None
    assert "DESCANSAR" in msg
    assert "puxar" not in msg.lower()
    assert "confiança" not in msg.lower()


def test_doenca_um_toque_por_episodio():
    """Já falou nesse episódio de doença -> não repete todo dia."""

    ill = SimpleNamespace(day="2026-08-13")

    assert _block(READINESS_GREEN, flag=True, illness=ill, already_sent=True) is None


def test_sem_doenca_segue_fluxo_normal():
    """Sem doença recente, o verde de dia puxado sai normalmente."""

    assert _block(READINESS_GREEN, flag=True, illness=None) is not None


def test_message_green_cita_positivo():

    v = ReadinessVerdict(
        tier=READINESS_GREEN, reason="x", should_speak=True,
        body_state="FRESH", signals=("seu HRV vem subindo",),
    )

    msg = ReadinessNotifier._message(v)

    assert "hrv vem subindo" in msg.lower()
    assert "confiança" in msg


def test_join_pt():

    assert ReadinessNotifier._join_pt(()) == ""
    assert ReadinessNotifier._join_pt(("a",)) == "a"
    assert ReadinessNotifier._join_pt(("a", "b")) == "a e b"
    assert ReadinessNotifier._join_pt(("a", "b", "c")) == "a, b e c"
