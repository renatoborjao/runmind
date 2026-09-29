import asyncio
from datetime import datetime, time
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
    has_garmin=True,
    is_race_day=False,
    deadline=time(11, 0),
    probe=None,
    still_asleep=False,
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
        patch(f"{MODULE}.GarminClient") as garmin,
        patch(
            f"{MODULE}.MorningBriefingNotifier._night_data_ready",
            return_value=data_ready,
        ),
        patch(
            f"{MODULE}.MorningBriefingNotifier._is_race_day",
            return_value=is_race_day,
        ),
        patch(
            f"{MODULE}.MorningBriefingNotifier._deadline",
            return_value=deadline,
        ),
        patch(
            f"{MODULE}.MorningBriefingNotifier._body_followup",
            new_callable=AsyncMock,
        ) as followup,
        patch(
            f"{MODULE}.MorningBriefingNotifier._still_asleep",
            return_value=still_asleep,
        ),
    ):

        now_in.return_value = datetime(2026, 7, 14, hour, minute)
        guard.already_sent.return_value = already_sent

        # has_garmin = is_connected AND analysis_enabled
        garmin.is_connected.return_value = has_garmin
        garmin.analysis_enabled.return_value = has_garmin

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

        # o que foi marcado no guard e se o complemento do corpo foi chamado
        if probe is not None:

            probe["marks"] = [c.args[0] for c in guard.mark.call_args_list]
            probe["followup"] = followup.await_count

        # como o treino foi cumprimentado? (só quando algo foi enviado, pra não
        # sujar os casos de silêncio que asseguram sent == {})
        if "message" in sent and daily.build.await_args is not None:

            sent["greet"] = daily.build.await_args.kwargs.get("greet")

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


def test_corpo_cumprimenta_entao_treino_nao_repete_bom_dia():
    """Bug real (02/08): a leitura de corpo abre com "Bom dia!" E o treino
    abria com "Bom dia, Renato!" — dois "bom dia" na mesma mensagem. Com
    bloco de corpo presente, o treino tem que vir SEM saudação (greet=False)."""

    sent = _run(
        missed=None,
        today="🏃 Hoje: 8km",
        data_ready=True,
        readiness="Bom dia! Seu HRV vem subindo, corpo recuperado.",
    )

    assert sent["greet"] is False


def test_treino_sozinho_cumprimenta():
    """Sem bloco de corpo (neutro/flag off), o treino LIDERA a mensagem e
    carrega o "Bom dia" (greet=True) — senão o briefing sai sem saudação."""

    sent = _run(
        missed=None,
        today="🏃 Hoje: 8km",
        data_ready=True,
        readiness=None,
    )

    assert sent["greet"] is True


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


def test_sem_relogio_rede_das_06h():
    """Sem Garmin: rede das 06h — manda furo + treino, SEM o bloco de corpo
    (não há dado da noite pra esperar), mesmo que houvesse alerta."""

    sent = _run(
        missed="Furou ontem",
        today="🏃 Hoje: 8km",
        data_ready=False,
        has_garmin=False,
        readiness="NÃO DEVERIA APARECER",
        hour=6,
    )

    assert sent["message"] == "Furou ontem\n\n🏃 Hoje: 8km"


def test_com_garmin_segura_o_briefing_ate_o_dado_chegar():
    """Com Garmin mas o dado ainda não sincronizou (10h): SEGURA o briefing
    inteiro — nada sai, nem o furo (pra nunca soltar o 'bom dia' sem o corpo
    de quem tem como medir). Era o bug da Fernanda: às 06h mandava sem corpo."""

    sent = _run(
        missed="Furou ontem",
        today="🏃 Hoje: 8km",
        data_ready=False,
        has_garmin=True,
        readiness="NÃO DEVERIA APARECER",
        hour=10,
    )

    assert sent == {}


def test_com_garmin_ultima_rede_11h_manda_sem_corpo():
    """Garmin que não sincronizou até as 11h (não dormiu com o relógio):
    desiste de esperar e manda furo + treino SEM o corpo — falha nunca
    vira silêncio."""

    sent = _run(
        missed="Furou ontem",
        today="🏃 Hoje: 8km",
        data_ready=False,
        has_garmin=True,
        readiness="NÃO DEVERIA APARECER",
        hour=11,
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
    """Passou das 11h30 (fim da janela): nada sai, nem com dado."""

    sent = _run(missed="Furou", today="🏃 Hoje", data_ready=True, hour=12)

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


def test_dia_da_prova_o_briefing_cede_pro_companheiro():
    """No dia da prova-alvo o briefing de rotina NÃO fala — quem conduz é o
    companheiro de prova (o 'É HOJE! 🏁'). Nada de tratar a prova como 'mais um
    treino' com clima 'boas pra treinar'. Era a queixa do Renato na manhã da
    prova. Mesmo com furo/corpo/treino prontos, sai silêncio."""

    sent = _run(
        missed="Furou ontem",
        today="🏃 Hoje: Prova-Âncora 10K",
        data_ready=True,
        readiness="Bom dia! Corpo recuperado.",
        hour=6,
        is_race_day=True,
    )

    assert sent == {}


def test_is_race_day_true_only_on_the_race_date():
    """O helper: True só quando a data da prova é HOJE; sem prova ou fora da
    data, False (e falha ao montar o goal não cala o briefing)."""

    from datetime import date

    from app.domain.entities.training_goal import TrainingGoal

    def _goal(race_date):
        return TrainingGoal(
            name="10k", distance_km=10.0,
            target_time=None, race_date=race_date,
        )

    with (
        patch(f"{MODULE}.BuildTrainingGoal") as build_goal,
        patch(f"{MODULE}.today_local", return_value=date(2026, 8, 23)),
    ):

        build_goal.execute.return_value = _goal(date(2026, 8, 23))
        assert MorningBriefingNotifier._is_race_day(RUNNER) is True

        build_goal.execute.return_value = _goal(date(2026, 8, 24))
        assert MorningBriefingNotifier._is_race_day(RUNNER) is False

        build_goal.execute.return_value = _goal(None)
        assert MorningBriefingNotifier._is_race_day(RUNNER) is False

        build_goal.execute.side_effect = RuntimeError("boom")
        assert MorningBriefingNotifier._is_race_day(RUNNER) is False


# --- _night_data_ready: o âncora é o SONO de hoje, não "existe registro" ---


def _ready(existing, fetched=None, fetch_error=None):

    from datetime import date

    from app.domain.entities.daily_health import DailyHealth

    with (
        patch(f"{MODULE}.GarminClient") as garmin,
        patch(f"{MODULE}.GarminHealthRepository") as repo_cls,
        patch(f"{MODULE}.GarminHealthSource") as source,
    ):

        garmin.is_connected.return_value = True
        garmin.analysis_enabled.return_value = True

        repo = repo_cls.return_value
        repo.get.return_value = (
            DailyHealth(date="2026-09-29", **existing) if existing else None
        )

        if fetch_error:
            source.sleep_closed.side_effect = fetch_error
        else:
            source.sleep_closed.return_value = bool(
                fetched and fetched.get("sleep_hours") is not None
            )
            source.fetch.return_value = (
                DailyHealth(date="2026-09-29", **fetched) if fetched else None
            )

        ready = MorningBriefingNotifier._night_data_ready(
            "renato2", date(2026, 9, 29)
        )

    return ready, repo, source


def test_parcial_da_madrugada_sem_sono_nao_conta_como_acordou():
    """Caso real 29/09: o poller gravou hoje só com stress/SpO2 de madrugada;
    o Garmin ainda não tem o sono. NÃO pode liberar o 'bom dia' às 04h30."""

    ready, repo, source = _ready(
        existing={"stress_avg": 35, "spo2_avg": 95},
        fetched={"stress_avg": 36},
    )

    assert ready is False
    # só a sonda de 1 chamada — o retrato completo espera o sono fechar
    source.sleep_closed.assert_called_once()
    source.fetch.assert_not_called()
    repo.upsert.assert_not_called()


def test_sono_ja_ingerido_libera_sem_bater_na_api():

    ready, repo, source = _ready(existing={"sleep_hours": 7.6})

    assert ready is True
    source.sleep_closed.assert_not_called()
    source.fetch.assert_not_called()


def test_sono_chega_e_mescla_sobre_o_parcial_sem_apagar():

    ready, repo, _ = _ready(
        existing={"stress_avg": 35, "spo2_avg": 95},
        fetched={"sleep_hours": 7.65, "hrv_last_night": 44},
    )

    assert ready is True

    saved = repo.upsert.call_args.args[1]

    assert saved.sleep_hours == 7.65
    assert saved.hrv_last_night == 44
    assert saved.spo2_avg == 95  # o parcial da madrugada ficou


def test_fetch_falha_segura_o_briefing():

    ready, _, _ = _ready(existing=None, fetch_error=RuntimeError("429"))

    assert ready is False


# --- prazo pessoal: o treino não espera o sync do sono ---


def test_sono_atrasado_estoura_o_prazo_e_manda_o_treino_sem_o_corpo():
    """Corre 05h20: prazo 04h50. Sono não sincronizou às 04h50 → sai furo +
    treino (sem corpo) e o corpo fica DEVENDO pro complemento."""

    probe = {}

    sent = _run(
        missed=None,
        today="🏃 Hoje: limiar",
        data_ready=False,
        hour=4,
        minute=50,
        deadline=time(4, 50),
        probe=probe,
    )

    assert sent["message"] == "🏃 Hoje: limiar"
    assert probe["marks"] == ["briefing", "briefing_body_due"]


def test_antes_do_prazo_segue_esperando_o_sono():

    sent = _run(
        missed=None,
        today="🏃 Hoje: limiar",
        data_ready=False,
        hour=4,
        minute=30,
        deadline=time(5, 0),
    )

    assert sent == {}


def test_decide_no_ultimo_tick_antes_do_prazo():
    """Tick de 5 min: às 04h56 o próximo tick (05h01) já passaria do prazo
    das 05h00 — manda agora, não depois."""

    sent = _run(
        missed=None,
        today="🏃 Hoje: limiar",
        data_ready=False,
        hour=4,
        minute=56,
        deadline=time(5, 0),
    )

    assert sent["message"] == "🏃 Hoje: limiar"


def test_sono_chegou_antes_do_prazo_nao_deixa_corpo_devendo():

    probe = {}

    sent = _run(
        missed=None,
        today="🏃 Hoje: limiar",
        data_ready=True,
        readiness="Bom dia! Corpo ok.",
        hour=4,
        minute=40,
        deadline=time(4, 50),
        probe=probe,
    )

    assert sent["message"].startswith("Bom dia! Corpo ok.")
    assert probe["marks"] == ["briefing"]


def test_sem_relogio_que_treina_cedo_recebe_antes_das_06h():

    sent = _run(
        missed=None,
        today="🏃 Hoje: rodagem",
        has_garmin=False,
        hour=5,
        minute=0,
        deadline=time(5, 0),
    )

    assert sent["message"] == "🏃 Hoje: rodagem"


def test_bom_dia_ja_enviado_chama_so_o_complemento_do_corpo():

    probe = {}

    sent = _run(
        missed="Furou", today="🏃 Hoje", hour=7, already_sent=True, probe=probe,
    )

    assert sent == {}
    assert probe["followup"] == 1


# --- complemento do corpo (sono chegou depois do bom dia) ---


def _followup(*, due=True, done=False, data_ready=True, ran_today=False,
              readiness=None, proposal=None):

    from datetime import date

    state = {"briefing_body_due": due, "briefing_body": done}
    sent = {}

    with (
        patch(f"{MODULE}.DispatchGuard") as guard,
        patch(f"{MODULE}.ReadinessNotifier") as readiness_mod,
        patch(f"{MODULE}.BodyConductProposer") as proposer,
        patch(f"{MODULE}.CoachOutbox") as outbox,
        patch(
            f"{MODULE}.MorningBriefingNotifier._night_data_ready",
            return_value=data_ready,
        ),
        patch(
            f"{MODULE}.MorningBriefingNotifier._ran_today",
            return_value=ran_today,
        ),
    ):

        guard.already_sent.side_effect = lambda kind, p, period: state[kind]
        readiness_mod.block = AsyncMock(return_value=readiness)
        proposer.for_briefing = AsyncMock(return_value=proposal)

        async def _capture(runner, message, **kwargs):
            sent["message"] = message
            sent["kind"] = kwargs.get("kind")

        outbox.send = AsyncMock(side_effect=_capture)

        asyncio.run(
            MorningBriefingNotifier._body_followup(
                RUNNER, "renato2", "2026-09-29", date(2026, 9, 29)
            )
        )

        sent["marks"] = [c.args[0] for c in guard.mark.call_args_list]

    return sent


def test_complemento_manda_o_corpo_quando_o_sono_chega_antes_do_treino():

    sent = _followup(readiness="Bom dia! Teu HRV caiu, pega leve.")

    assert sent["message"] == "Bom dia! Teu HRV caiu, pega leve."
    assert sent["kind"] == "morning_body"
    assert sent["marks"] == ["briefing_body"]


def test_complemento_leva_a_proposta_de_aliviar_em_sobrecarga():

    sent = _followup(proposal="Bom dia! Corpo em sobrecarga — alivio hoje?")

    assert sent["message"].startswith("Bom dia! Corpo em sobrecarga")


def test_complemento_calado_se_ja_treinou():

    sent = _followup(ran_today=True, readiness="Bom dia! Pega leve.")

    assert "message" not in sent
    assert sent["marks"] == ["briefing_body"]


def test_complemento_calado_quando_o_corpo_nao_tem_o_que_dizer():

    sent = _followup()

    assert "message" not in sent


def test_complemento_espera_o_sono_sem_gastar_a_decisao():

    sent = _followup(data_ready=False, readiness="Bom dia!")

    assert "message" not in sent
    assert sent["marks"] == []


def test_complemento_so_quando_o_bom_dia_saiu_sem_o_corpo():

    sent = _followup(due=False, readiness="Bom dia!")

    assert "message" not in sent


def test_complemento_uma_vez_por_dia():

    sent = _followup(done=True, readiness="Bom dia!")

    assert "message" not in sent


def test_um_tick_antes_da_ultima_janela_ainda_espera():

    sent = _run(
        missed=None,
        today="🏃 Hoje: limiar",
        data_ready=False,
        hour=4,
        minute=54,
        deadline=time(5, 0),
    )

    assert sent == {}



# --- amarrado ao sono: passou do prazo, mas o relógio prova que ele dorme ---


def test_passou_do_prazo_mas_relogio_prova_que_dorme_segura():
    """Caso real 29/09: renato2 dormiu até 07h28 num dia de treino cedo. Prazo
    04h55, mas o relógio sincronizou há pouco com o sono aberto → segura."""

    sent = _run(
        missed=None,
        today="🏃 Hoje: limiar",
        data_ready=False,
        hour=5,
        minute=0,
        deadline=time(4, 55),
        still_asleep=True,
    )

    assert sent == {}


def test_passou_do_prazo_sem_prova_de_sono_manda():

    sent = _run(
        missed=None,
        today="🏃 Hoje: limiar",
        data_ready=False,
        hour=5,
        minute=0,
        deadline=time(4, 55),
        still_asleep=False,
    )

    assert sent["message"] == "🏃 Hoje: limiar"


def test_dormindo_nao_segura_alem_do_teto_das_11h():

    sent = _run(
        missed=None,
        today="🏃 Hoje: limiar",
        data_ready=False,
        hour=10,
        minute=55,
        deadline=time(4, 55),
        still_asleep=True,
    )

    assert sent["message"] == "🏃 Hoje: limiar"


# --- _still_asleep: sync recente com o sono aberto = dormindo ---


def _asleep(last_sync, now):

    with patch(f"{MODULE}.GarminHealthSource") as source:

        if isinstance(last_sync, Exception):
            source.last_sync_at.side_effect = last_sync
        else:
            source.last_sync_at.return_value = last_sync

        return MorningBriefingNotifier._still_asleep("renato2", now)


_NOW = datetime(2026, 9, 29, 7, 55, tzinfo=__import__("datetime").timezone.utc)


def test_sync_de_10_min_atras_com_sono_aberto_esta_dormindo():

    from datetime import timedelta

    assert _asleep(_NOW - timedelta(minutes=10), _NOW) is True


def test_sync_velho_nao_prova_nada():

    from datetime import timedelta

    assert _asleep(_NOW - timedelta(minutes=40), _NOW) is False


def test_sync_desconhecido_ou_erro_nao_segura():

    assert _asleep(None, _NOW) is False
    assert _asleep(RuntimeError("429"), _NOW) is False
