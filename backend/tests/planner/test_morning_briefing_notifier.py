import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

from app.application.planner.morning_briefing_notifier import (
    MorningBriefingNotifier,
)
from tests.coach.factories import make_runner

MODULE = "app.application.planner.morning_briefing_notifier"

RUNNER = make_runner()


def _run(
    missed,
    today,
    *,
    hour=6,
    minute=0,
    data_ready=False,
    readiness=None,
    proposal=None,
    already_sent=False,
):

    sent = {}

    with (
        patch(f"{MODULE}.MissedWorkoutFlow") as flow,
        patch(f"{MODULE}.DailyTrainingNotifier") as daily,
        patch(f"{MODULE}.ReadinessNotifier") as readiness_mod,
        patch(f"{MODULE}.BodyConductProposer") as proposer,
        patch(f"{MODULE}.CoachOutbox") as notifier,
        patch(f"{MODULE}.LoadRunnerProfile") as load_runner,
        patch(f"{MODULE}.now_in") as now_in,
        patch(f"{MODULE}.DispatchGuard") as guard,
        patch(
            f"{MODULE}.MorningBriefingNotifier._night_data_ready",
            return_value=data_ready,
        ),
    ):

        now_in.return_value = datetime(2026, 7, 14, hour, minute)
        guard.already_sent.return_value = already_sent

        load_runner.execute.return_value = RUNNER

        flow.process = AsyncMock(
            return_value=(RUNNER, missed) if missed else None
        )
        daily.build = AsyncMock(
            return_value=(RUNNER, today) if today else None
        )
        readiness_mod.block = AsyncMock(return_value=readiness)
        proposer.for_briefing = AsyncMock(return_value=proposal)

        async def _capture(runner, message, **kwargs):
            sent["runner"] = runner
            sent["message"] = message
            sent["kwargs"] = kwargs

        notifier.send = AsyncMock(side_effect=_capture)

        asyncio.run(MorningBriefingNotifier._notify_one("renato"))

    return sent


def test_despertar_junta_furo_prontidao_e_treino_na_ordem():
    """Com dado da noite: furo -> corpo/prontidão -> treino, numa mensagem só."""

    sent = _run(
        missed="Furou ontem — quer que eu ajuste?",
        today="🏃 Hoje: 8km",
        data_ready=True,
        readiness="Reparei que seu HRV vem caindo — pega leve.",
        hour=6,
    )

    assert sent["message"] == (
        "Furou ontem — quer que eu ajuste?\n\n"
        "Reparei que seu HRV vem caindo — pega leve.\n\n"
        "🏃 Hoje: 8km"
    )


def test_proposta_strained_entra_e_suprime_o_treino_repetido():
    """Corpo em sobrecarga: a PROPOSTA de aliviar o treino de hoje entra no
    lugar da prontidão (readiness None) e o bloco de treino é SUPRIMIDO — a
    proposta já fala do treino, não repete."""

    sent = _run(
        missed=None,
        today="🏃 Hoje: Intervalado de Limiar 7km",
        data_ready=True,
        readiness=None,
        proposal="Teu corpo pediu freio hoje. Troco o Limiar por leve? (sim)",
    )

    assert sent["message"] == (
        "Teu corpo pediu freio hoje. Troco o Limiar por leve? (sim)"
    )
    assert "Intervalado" not in sent["message"]   # treino não repete


def test_prontidao_ganha_da_proposta_e_treino_segue():
    """Prontidão (CAUTION/GREEN) fala -> nem chama a proposta, e o treino de
    hoje segue no fim (o aviso é genérico, o treino complementa)."""

    sent = _run(
        missed=None,
        today="🏃 Hoje: 8km",
        data_ready=True,
        readiness="Reparei que seu HRV vem caindo — pega leve.",
        proposal="NÃO DEVERIA APARECER",
    )

    assert sent["message"] == (
        "Reparei que seu HRV vem caindo — pega leve.\n\n🏃 Hoje: 8km"
    )


def test_prontidao_so_entra_com_dado_da_noite():
    """Sem dado (rede das 06h): manda furo + treino, SEM o bloco de corpo,
    mesmo que houvesse alerta."""

    sent = _run(
        missed="Furou ontem",
        today="🏃 Hoje: 8km",
        data_ready=False,
        readiness="NÃO DEVERIA APARECER",
        hour=6,
    )

    assert sent["message"] == "Furou ontem\n\n🏃 Hoje: 8km"


def test_sem_bloco_de_corpo_quando_neutro():
    """Dado chegou, mas prontidão devolve None (neutro/flag off): furo +
    treino seguem."""

    sent = _run(
        missed=None, today="🏃 Hoje: tiros", data_ready=True, readiness=None,
    )

    assert sent["message"] == "🏃 Hoje: tiros"


def test_espera_o_despertar_antes_das_06h():
    """Cedo (05:00) e sem dado ainda: não manda nada — espera o próximo tick."""

    sent = _run(
        missed="Furou ontem", today="🏃 Hoje",
        data_ready=False, hour=5, minute=0,
    )

    assert sent == {}


def test_despertar_cedo_manda_na_hora():
    """Acordou 05:15 e o dado chegou: manda já (não espera as 06h)."""

    sent = _run(
        missed=None, today="🏃 Hoje: 10km",
        data_ready=True, hour=5, minute=15,
    )

    assert sent["message"] == "🏃 Hoje: 10km"


def test_fora_da_janela_nada_sai():

    sent = _run(missed="Furou", today="🏃 Hoje", data_ready=True, hour=11)

    assert sent == {}


def test_dedup_um_bom_dia_por_dia():

    sent = _run(
        missed="Furou", today="🏃 Hoje", data_ready=True,
        hour=6, already_sent=True,
    )

    assert sent == {}


def test_silencio_quando_nao_ha_nada_a_dizer():
    """Sem furo, sem alerta, hoje é descanso: silêncio (mas marca o dia)."""

    sent = _run(missed=None, today=None, data_ready=True, hour=6)

    assert sent == {}
