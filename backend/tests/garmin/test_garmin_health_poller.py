import asyncio
from contextlib import ExitStack
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.application.garmin import garmin_health_poller as module
from app.application.garmin.garmin_health_poller import GarminHealthPoller
from app.domain.entities.daily_health import DailyHealth

MODULE = "app.application.garmin.garmin_health_poller"


def _runner(tz="America/Sao_Paulo"):

    return SimpleNamespace(timezone=tz)


def _repo_with(records=None):
    """MagicMock repo cujo get(profile, day) devolve records.get(day) — deixa
    cada teste montar o estado do disco por data."""

    records = records or {}

    repo = MagicMock()

    repo.get.side_effect = lambda profile, day: records.get(day)

    return repo


def _poll_patches(fetch, profile_repo):
    """now_in fixo (hoje = 2026-07-21, ontem = 2026-07-20), profile carregado,
    fonte mockada e as varreduras (VO₂máx/contexto/prova) neutralizadas."""

    return (
        patch(f"{MODULE}.now_in", return_value=datetime(2026, 7, 21, 8, 0)),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
        patch(f"{MODULE}.GarminHealthSource.fetch", fetch),
        patch.object(GarminHealthPoller, "sync_vo2max", return_value=0),
        patch.object(GarminHealthPoller, "sync_body_context", return_value=0),
        patch.object(GarminHealthPoller, "sync_race_predictions", return_value=False),
    )


def test_finaliza_ontem_e_semeia_hoje_no_mesmo_tick():
    """Disco vazio: o poll finaliza ONTEM (dia fechado, is_final) E semeia HOJE
    (prontidão da manhã, is_final=False) no mesmo tick — leitura same-day."""

    repo = _repo_with({})

    profile_repo = MagicMock()

    profile_repo.load.return_value = _runner()

    fetch = MagicMock(
        side_effect=lambda p, d: DailyHealth(date=d, sleep_hours=7.0, sleep_score=70)
    )

    with ExitStack() as stack:

        for _p in _poll_patches(fetch, profile_repo):

            stack.enter_context(_p)

        GarminHealthPoller.poll_one("renato2", repo)

    fetched = sorted(c.args[1] for c in fetch.call_args_list)

    assert fetched == ["2026-07-20", "2026-07-21"]

    saved = {c.args[1].date: c.args[1] for c in repo.upsert.call_args_list}

    assert saved["2026-07-20"].is_final is True    # ontem: dia fechado

    assert saved["2026-07-21"].is_final is False   # hoje: parcial, atualizável


def test_hoje_oco_so_com_stress_e_re_buscado_ate_a_manha_cair():
    """Regressão (o bug do 'dormi e acordei sem'): o relógio sincroniza o AGORA
    (stress/SpO2/bateria corrente) antes do sono da noite. Esse dia tem
    has_data=True mas NÃO tem a leitura da manhã — o poll deve continuar puxando
    HOJE (guarda por has_recovery, não has_data), senão o dia fica oco o dia todo
    e o herói do corpo em branco. Ontem já finalizado isola o teste em hoje."""

    records = {
        "2026-07-20": DailyHealth(date="2026-07-20", sleep_score=70, is_final=True),
        # hoje nasceu oco: só stress (has_data=True, has_recovery=False)
        "2026-07-21": DailyHealth(date="2026-07-21", stress_avg=30),
    }

    repo = _repo_with(records)

    profile_repo = MagicMock()

    profile_repo.load.return_value = _runner()

    # agora a manhã caiu: o fetch de hoje traz sono/HRV
    fetch = MagicMock(
        side_effect=lambda p, d: DailyHealth(date=d, sleep_hours=7.5, hrv_last_night=40)
    )

    with ExitStack() as stack:

        for _p in _poll_patches(fetch, profile_repo):

            stack.enter_context(_p)

        GarminHealthPoller.poll_one("renato2", repo)

    # re-buscou HOJE (não parou no dado oco) e não tocou ONTEM (já final)
    fetched = [c.args[1] for c in fetch.call_args_list]

    assert "2026-07-21" in fetched

    assert "2026-07-20" not in fetched

    saved = {c.args[1].date: c.args[1] for c in repo.upsert.call_args_list}

    hoje = saved["2026-07-21"]

    assert hoje.sleep_hours == 7.5          # a manhã entrou
    assert hoje.stress_avg == 30            # e o que já havia não sumiu
    assert hoje.is_final is False


def test_nao_rebusca_ontem_final_nem_hoje_ja_capturado():
    """Gentileza com a API: ontem já finalizado e hoje já com a manhã capturada
    → nenhuma chamada nova ao Garmin (na série)."""

    records = {
        "2026-07-20": DailyHealth(date="2026-07-20", sleep_score=70, is_final=True),
        "2026-07-21": DailyHealth(date="2026-07-21", sleep_hours=7.0),
    }

    repo = _repo_with(records)

    profile_repo = MagicMock()

    profile_repo.load.return_value = _runner()

    fetch = MagicMock()

    with ExitStack() as stack:

        for _p in _poll_patches(fetch, profile_repo):

            stack.enter_context(_p)

        GarminHealthPoller.poll_one("renato2", repo)

    fetch.assert_not_called()

    repo.upsert.assert_not_called()


def test_finalizar_ontem_nao_apaga_a_manha_ja_capturada():
    """Ontem nasceu parcial como 'hoje' (tinha o sono da manhã). Ao fechar, o
    fetch de finalização traz a carga do dia mas o sono veio None nessa passada
    (endpoint instável) — o merge NÃO pode apagar o sono que já havia."""

    partial = DailyHealth(
        date="2026-07-20", sleep_hours=7.0, sleep_score=72, is_final=False
    )

    records = {
        "2026-07-20": partial,
        # hoje já capturado → isola o teste no fechamento de ontem
        "2026-07-21": DailyHealth(date="2026-07-21", sleep_hours=6.0),
    }

    repo = _repo_with(records)

    profile_repo = MagicMock()

    profile_repo.load.return_value = _runner()

    # fechamento de ontem: passos + FC repouso cheios, mas SEM sono nesta passada
    fetch = MagicMock(
        side_effect=lambda p, d: DailyHealth(date=d, steps=12000, resting_hr=48)
    )

    with ExitStack() as stack:

        for _p in _poll_patches(fetch, profile_repo):

            stack.enter_context(_p)

        GarminHealthPoller.poll_one("renato2", repo)

    saved = {c.args[1].date: c.args[1] for c in repo.upsert.call_args_list}

    assert "2026-07-21" not in saved            # hoje não foi re-buscado

    ontem = saved["2026-07-20"]

    assert ontem.is_final is True

    assert ontem.steps == 12000                 # veio do fechamento

    assert ontem.resting_hr == 48

    assert ontem.sleep_hours == 7.0             # a manhã NÃO foi apagada

    assert ontem.sleep_score == 72


def test_sync_vo2max_fills_missing_days():
    """A varredura preenche o VO₂máx dos dias que a série não tinha — o dado que
    existe na API mas o poll de 'ontem, 1x' nunca capturava."""

    repo = MagicMock()

    repo.load.return_value = []  # série sem nenhum VO₂máx

    profile_repo = MagicMock()

    profile_repo.load.return_value = _runner()

    # o Garmin só tem VO₂máx no dia 20 (esporádico); os outros vêm vazios
    def vo2(garmin, day):

        return 45.2 if day == "2026-07-20" else None

    with (
        patch(f"{MODULE}.now_in", return_value=datetime(2026, 7, 21, 8, 0)),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
        patch(f"{MODULE}.GarminClient.is_connected", return_value=True),
        patch(f"{MODULE}.GarminClient.analysis_enabled", return_value=True),
        patch(f"{MODULE}.GarminClient.connect", return_value=MagicMock()),
        patch(f"{MODULE}.GarminHealthSource.vo2max_for", side_effect=vo2),
        patch(f"{MODULE}.time.sleep"),
    ):

        filled = GarminHealthPoller.sync_vo2max("renato2", days=3, repo=repo)

    assert filled == 1

    saved = repo.upsert.call_args[0][1]

    assert saved.date == "2026-07-20"
    assert saved.vo2max == 45.2


def test_sync_vo2max_skips_days_already_filled():
    """Dia que já tem VO₂máx não bate na API (idempotente, gentil com a API)."""

    repo = MagicMock()

    repo.load.return_value = [DailyHealth(date="2026-07-20", vo2max=44.0)]

    profile_repo = MagicMock()

    profile_repo.load.return_value = _runner()

    seen = []

    def vo2(garmin, day):

        seen.append(day)

        return None

    with (
        patch(f"{MODULE}.now_in", return_value=datetime(2026, 7, 21, 8, 0)),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
        patch(f"{MODULE}.GarminClient.is_connected", return_value=True),
        patch(f"{MODULE}.GarminClient.analysis_enabled", return_value=True),
        patch(f"{MODULE}.GarminClient.connect", return_value=MagicMock()),
        patch(f"{MODULE}.GarminHealthSource.vo2max_for", side_effect=vo2),
        patch(f"{MODULE}.time.sleep"),
    ):

        GarminHealthPoller.sync_vo2max("renato2", days=3, repo=repo)

    # o dia 20 (já com VO₂máx) não foi consultado na API
    assert "2026-07-20" not in seen

    repo.upsert.assert_not_called()


def test_sync_body_context_enriches_existing_days():
    """A varredura mescla carga de vida + body battery nos dias que já eram
    snapshot mas ainda não tinham o campo (backfill do histórico recente)."""

    repo = MagicMock()

    repo.load.return_value = [DailyHealth(date="2026-07-20", sleep_score=70)]

    profile_repo = MagicMock()

    profile_repo.load.return_value = _runner()

    def ctx(garmin, day):

        if day == "2026-07-20":

            return {"steps": 5000, "body_battery_most_recent": 40}

        return {}

    with (
        patch(f"{MODULE}.now_in", return_value=datetime(2026, 7, 21, 8, 0)),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
        patch(f"{MODULE}.GarminClient.is_connected", return_value=True),
        patch(f"{MODULE}.GarminClient.analysis_enabled", return_value=True),
        patch(f"{MODULE}.GarminClient.connect", return_value=MagicMock()),
        patch(f"{MODULE}.GarminHealthSource.body_context_for", side_effect=ctx),
        patch(f"{MODULE}.time.sleep"),
    ):

        filled = GarminHealthPoller.sync_body_context("renato2", days=3, repo=repo)

    assert filled == 1

    saved = repo.upsert.call_args[0][1]

    assert saved.date == "2026-07-20"
    assert saved.steps == 5000
    assert saved.body_battery_most_recent == 40
    assert saved.sleep_score == 70  # não apagou o que já havia


def test_sync_body_context_does_not_create_new_days():
    """Contexto não vale um dia novo: dia sem snapshot é ignorado (nem chama a
    API), diferente do VO₂máx que pode criar o dia."""

    repo = MagicMock()

    repo.load.return_value = []  # nenhum dia rastreado

    profile_repo = MagicMock()

    profile_repo.load.return_value = _runner()

    seen = []

    def ctx(garmin, day):

        seen.append(day)

        return {"steps": 5000, "body_battery_most_recent": 40}

    with (
        patch(f"{MODULE}.now_in", return_value=datetime(2026, 7, 21, 8, 0)),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
        patch(f"{MODULE}.GarminClient.is_connected", return_value=True),
        patch(f"{MODULE}.GarminClient.analysis_enabled", return_value=True),
        patch(f"{MODULE}.GarminClient.connect", return_value=MagicMock()),
        patch(f"{MODULE}.GarminHealthSource.body_context_for", side_effect=ctx),
        patch(f"{MODULE}.time.sleep"),
    ):

        filled = GarminHealthPoller.sync_body_context("renato2", days=3, repo=repo)

    assert filled == 0
    assert seen == []                 # nem bateu na API
    repo.upsert.assert_not_called()


def test_sync_body_context_skips_days_already_filled():
    """Dia que já tem body battery não bate na API (idempotente)."""

    repo = MagicMock()

    repo.load.return_value = [
        DailyHealth(date="2026-07-20", sleep_score=70,
                    body_battery_most_recent=40)
    ]

    profile_repo = MagicMock()

    profile_repo.load.return_value = _runner()

    seen = []

    def ctx(garmin, day):

        seen.append(day)

        return {}

    with (
        patch(f"{MODULE}.now_in", return_value=datetime(2026, 7, 21, 8, 0)),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
        patch(f"{MODULE}.GarminClient.is_connected", return_value=True),
        patch(f"{MODULE}.GarminClient.analysis_enabled", return_value=True),
        patch(f"{MODULE}.GarminClient.connect", return_value=MagicMock()),
        patch(f"{MODULE}.GarminHealthSource.body_context_for", side_effect=ctx),
        patch(f"{MODULE}.time.sleep"),
    ):

        GarminHealthPoller.sync_body_context("renato2", days=3, repo=repo)

    assert "2026-07-20" not in seen
    repo.upsert.assert_not_called()


def test_sync_body_context_skips_athletes_without_garmin():

    repo = MagicMock()

    connect = MagicMock()

    with (
        patch(f"{MODULE}.GarminClient.is_connected", return_value=False),
        patch(f"{MODULE}.GarminClient.analysis_enabled", return_value=False),
        patch(f"{MODULE}.GarminClient.connect", connect),
    ):

        filled = GarminHealthPoller.sync_body_context("helio", days=7, repo=repo)

    assert filled == 0

    connect.assert_not_called()

    repo.upsert.assert_not_called()


def test_poll_all_gates_on_connected_and_analysis_enabled():

    seen = []

    def fake_poll_one(profile, repo):

        seen.append(profile)

    profile_repo = MagicMock()

    profile_repo.list_all.return_value = ["conectado", "sem_garmin", "sem_valvula"]

    def connected(p):

        return p in ("conectado", "sem_valvula")

    def analysis(p):

        return p == "conectado"

    with (
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
        patch(f"{MODULE}.GarminClient.is_connected", side_effect=connected),
        patch(f"{MODULE}.GarminClient.analysis_enabled", side_effect=analysis),
        patch.object(GarminHealthPoller, "poll_one", staticmethod(fake_poll_one)),
    ):

        asyncio.run(GarminHealthPoller.poll_all())

    # só o atleta conectado E com a válvula ligada é ingerido
    assert seen == ["conectado"]


def test_seed_stops_at_start_of_watch_history():

    # 4 dias mais recentes com dado; antes disso o relógio nem existia (vazio)
    with_data = {"2026-07-20", "2026-07-19", "2026-07-18", "2026-07-17"}

    def fetch(profile, day):

        h = DailyHealth(date=day)

        if day in with_data:

            h.sleep_score = 70

        return h

    repo = MagicMock()

    repo.has_date.return_value = False

    profile_repo = MagicMock()

    profile_repo.load.return_value = _runner()

    with (
        patch(f"{MODULE}.now_in", return_value=datetime(2026, 7, 21, 8, 0)),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
        patch(f"{MODULE}.GarminHealthSource.fetch", side_effect=fetch),
        patch(f"{MODULE}.time.sleep"),
    ):

        pulled = GarminHealthPoller.seed_history("renato2", repo)

    # gravou só os 4 dias com dado, parou depois de 3 vazios seguidos
    assert pulled == 4
    assert repo.upsert.call_count == 4


def test_seed_skips_already_stored_days():

    def fetch(profile, day):

        return DailyHealth(date=day, sleep_score=70)

    repo = MagicMock()

    # 2026-07-20 já guardado; 07-19 e 07-18 novos; resto (vazio) fetch cobre
    stored = {"2026-07-20"}

    repo.has_date.side_effect = lambda p, d: d in stored

    profile_repo = MagicMock()

    profile_repo.load.return_value = _runner()

    calls = []

    def tracked_fetch(profile, day):

        calls.append(day)

        # só 07-19 e 07-18 tem dado; antes, vazio (para o loop)
        h = DailyHealth(date=day)

        if day in ("2026-07-19", "2026-07-18"):

            h.sleep_score = 70

        return h

    with (
        patch(f"{MODULE}.now_in", return_value=datetime(2026, 7, 21, 8, 0)),
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
        patch(f"{MODULE}.GarminHealthSource.fetch", side_effect=tracked_fetch),
        patch(f"{MODULE}.time.sleep"),
    ):

        GarminHealthPoller.seed_history("renato2", repo)

    # não buscou o dia já guardado (07-20 não entrou em calls)
    assert "2026-07-20" not in calls
    assert "2026-07-19" in calls


def test_sync_vo2max_skips_athletes_without_garmin():
    """Sem Garmin conectado: nem conecta, nem insere — VO₂máx é dado do relógio
    (o alerta do Renato: só pra quem tem Garmin)."""

    repo = MagicMock()

    connect = MagicMock()

    with (
        patch(f"{MODULE}.GarminClient.is_connected", return_value=False),
        patch(f"{MODULE}.GarminClient.analysis_enabled", return_value=False),
        patch(f"{MODULE}.GarminClient.connect", connect),
    ):

        filled = GarminHealthPoller.sync_vo2max("helio", days=10, repo=repo)

    assert filled == 0

    connect.assert_not_called()      # nem tentou logar no Garmin

    repo.upsert.assert_not_called()  # nada inserido


def test_sync_race_predictions_saves_when_data_and_connected():
    """Com Garmin conectado e projeção disponível: salva o estado."""

    from app.domain.entities.race_prediction import RacePrediction

    repo = MagicMock()

    pred = RacePrediction(time_10k_sec=3086)

    with (
        patch(f"{MODULE}.GarminClient.is_connected", return_value=True),
        patch(f"{MODULE}.GarminClient.analysis_enabled", return_value=True),
        patch(f"{MODULE}.GarminClient.connect", return_value=MagicMock()),
        patch(f"{MODULE}.GarminHealthSource.race_predictions_for", return_value=pred),
    ):

        ok = GarminHealthPoller.sync_race_predictions("renato2", repo=repo)

    assert ok is True

    repo.save.assert_called_once()


def test_sync_race_predictions_skips_without_garmin():

    repo = MagicMock()

    connect = MagicMock()

    with (
        patch(f"{MODULE}.GarminClient.is_connected", return_value=False),
        patch(f"{MODULE}.GarminClient.analysis_enabled", return_value=False),
        patch(f"{MODULE}.GarminClient.connect", connect),
    ):

        ok = GarminHealthPoller.sync_race_predictions("helio", repo=repo)

    assert ok is False

    connect.assert_not_called()

    repo.save.assert_not_called()


def test_poll_all_isolates_failure_per_athlete():

    def fake_poll_one(profile, repo):

        if profile == "quebra":

            raise RuntimeError("garmin fora")

    profile_repo = MagicMock()

    profile_repo.list_all.return_value = ["quebra", "ok"]

    done = []

    def tracking(profile, repo):

        fake_poll_one(profile, repo)

        done.append(profile)

    with (
        patch(f"{MODULE}.RunnerProfileRepository", return_value=profile_repo),
        patch(f"{MODULE}.GarminClient.is_connected", return_value=True),
        patch(f"{MODULE}.GarminClient.analysis_enabled", return_value=True),
        patch.object(GarminHealthPoller, "poll_one", staticmethod(tracking)),
    ):

        asyncio.run(GarminHealthPoller.poll_all())

    # a falha de um atleta não impede o próximo
    assert done == ["ok"]
