import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.application.coach.intelligence.personal_record_detector import (
    PersonalRecordDetector,
)
from app.infrastructure.persistence import (
    personal_record_repository as repo_module,
)
from app.infrastructure.persistence.personal_record_repository import (
    PersonalRecordRepository,
)
from tests.coach.factories import make_activity, make_runner

MODULE = "app.application.coach.intelligence.personal_record_detector"


@pytest.fixture(autouse=True)
def _tmp_storage(tmp_path, monkeypatch):

    monkeypatch.setattr(repo_module, "_STORAGE", tmp_path / "records")


def _run(day, month, distance_m, speed, id_, sport="Run"):

    return make_activity(
        id=id_,
        sport=sport,
        distance=distance_m,
        average_speed=speed,
        start_date=datetime(2026, month, day, 7, 0, 0),
    )


def _feed(runner, activities, has_token=True):
    """Roda o detector com o Strava dublado: `activities` já vem
    newest-first, como a API do Strava devolve de verdade. O caminho ao
    vivo busca só um punhado (não as 200 do cold-start) — mesmo mock
    serve pros dois, já que ambos chamam `get_last_activities`."""

    with (
        patch(f"{MODULE}.TokenStore") as mock_token_store,
        patch(f"{MODULE}.StravaClient") as mock_client_cls,
    ):

        mock_token_store.return_value.load.return_value = (
            {"access_token": "x"} if has_token else None
        )

        mock_client_cls.return_value.get_last_activities = AsyncMock(
            return_value=activities,
        )

        return asyncio.run(
            PersonalRecordDetector.after_feedback(runner),
        )


def test_athlete_without_strava_gets_no_celebration():

    runner = make_runner()

    assert _feed(runner, [], has_token=False) is None


def test_cold_start_seeds_and_stays_silent():

    runner = make_runner()

    current = _run(1, 7, 10_000, 3.33, 1)

    assert _feed(runner, [current]) is None


def test_longest_run_triggers_after_seed():

    runner = make_runner()

    first = _run(1, 7, 10_000, 3.33, 1)

    _feed(runner, [first])  # semeia (10km)

    second = _run(2, 7, 15_000, 3.33, 2)

    message = _feed(runner, [second, first])  # newest-first

    assert message is not None
    assert "15.0 km" in message


def test_trail_run_counts_toward_longest():
    """Corrida em trilha (TrailRun) também compete por recorde de corrida
    — só caminhada/hike (Walk/Hike) ficam de fora."""

    runner = make_runner()

    first = _run(1, 7, 10_000, 3.33, 1, sport="Run")

    _feed(runner, [first])

    trail = _run(2, 7, 15_000, 3.33, 2, sport="TrailRun")

    message = _feed(runner, [trail, first])

    assert message is not None
    assert "15.0 km" in message


def test_hike_does_not_count_as_longest_run():

    runner = make_runner()

    first = _run(1, 7, 10_000, 3.33, 1, sport="Run")

    _feed(runner, [first])

    hike = _run(2, 7, 20_000, 3.33, 2, sport="Hike")

    assert _feed(runner, [hike, first]) is None


def test_shorter_run_after_seed_does_not_trigger():

    runner = make_runner()

    first = _run(1, 7, 10_000, 3.33, 1)

    _feed(runner, [first])

    second = _run(2, 7, 8_000, 3.33, 2)

    assert _feed(runner, [second, first]) is None


def test_pace_band_triggers_with_margin_and_ignores_micro_improvement():

    runner = make_runner()

    # 6km @ pace 5:00/km (speed = 1000/(5*60) = 3.333...)
    first = _run(1, 7, 6_000, 1000 / (5 * 60), 1)

    _feed(runner, [first])  # semeia banda 5-8 com pace 5:00

    # melhora de 10s/km (bem acima da margem de 3s) -> dispara
    faster = _run(2, 7, 6_000, 1000 / (4.83 * 60), 2)

    message = _feed(runner, [faster, first])

    assert message is not None
    assert "mais rápido na faixa de 5-8" in message

    # segunda melhora, agora de ~1s/km (abaixo da margem) -> silêncio
    tiny_improvement = _run(3, 7, 6_000, 1000 / (4.81 * 60), 3)

    assert _feed(
        runner, [tiny_improvement, faster, first],
    ) is None


def test_km_milestone_crossed_updates_silently_without_celebrating():
    """Decisão do Renato: 'km acumulado' não é recorde de corredor de
    verdade — segue sendo rastreado (o recap mensal usa), mas não gera mais
    mensagem de comemoração depois de cada treino."""

    runner = make_runner()

    # 96km acumulados antes de hoje; corrida mais longa já semeada em
    # 15km, pra hoje (10km) não disparar OUTRO recorde e confundir o teste
    base = [
        _run(1, 6, 15_000, 3.0, 1),
        *[_run(d, 6, 9_000, 3.0, d) for d in range(2, 11)],
    ]

    _feed(runner, list(reversed(base)))  # semeia: 96km, longest=15km

    today = _run(1, 7, 10_000, 3.0, 100)  # empurra pra 106km -> cruza 100

    message = _feed(runner, [today] + list(reversed(base)))

    assert message is None  # sem comemoração — só atualiza por baixo

    records = PersonalRecordRepository().load(runner.id)

    assert records["total_km_accumulated"] == 106.0
    assert records["total_km_milestone"] == 100
    assert records["total_km_milestone_date"] == "2026-07-01"


def test_current_week_volume_updates_silently_without_celebrating():
    """Decisão do Renato: 'semana de maior volume' não é recorde de
    corredor de verdade — segue sendo rastreada (o recap mensal usa), mas
    não gera mais mensagem de comemoração."""

    runner = make_runner()

    # semana anterior: 20km (semente); corrida mais longa = 10km
    seed_week = [_run(2, 6, 10_000, 3.0, 2), _run(1, 6, 10_000, 3.0, 1)]

    _feed(runner, seed_week)

    # 3 corridas de 9km NA MESMA semana ISO nova somam 27km > 20km da
    # semente, mas nenhuma bate a corrida mais longa (10km) nem o pace
    # da faixa 8-12 (mesma velocidade da semente) -> sempre silêncio
    week2 = [
        _run(6, 7, 9_000, 3.0, 3),
        _run(8, 7, 9_000, 3.0, 4),
        _run(10, 7, 9_000, 3.0, 5),
    ]

    history_so_far = list(seed_week)

    for run in week2:

        message = _feed(runner, [run] + history_so_far)

        assert message is None

        history_so_far = [run] + history_so_far

    records = PersonalRecordRepository().load(runner.id)

    assert records["best_week_km"] == 27.0
    assert records["best_week_key"] == "2026-W28"
    assert records["current_week_km"] == 27.0


def test_reprocessing_same_activity_does_not_repeat_celebration():

    runner = make_runner()

    first = _run(1, 7, 10_000, 3.33, 1)

    _feed(runner, [first])

    second = _run(2, 7, 15_000, 3.33, 2)

    activities = [second, first]

    first_result = _feed(runner, activities)

    assert first_result is not None

    # reprocessar exatamente o mesmo treino (ex.: webhook duplicado, ou o
    # poller do Garmin rodando antes do Strava sincronizar de novo) não
    # dispara a mesma comemoração de novo
    second_result = _feed(runner, activities)

    assert second_result is None


def test_multiple_records_in_one_run_combine_into_one_message():

    runner = make_runner()

    # 6km @ pace 5:00/km
    first = _run(1, 7, 6_000, 1000 / (5 * 60), 1)

    _feed(runner, [first])  # semeia longest=6km, banda 5-8 @ 5:00/km

    # 7km @ pace 4:30/km: bate corrida mais longa E pace da mesma faixa
    better = _run(8, 7, 7_000, 1000 / (4.5 * 60), 2)

    message = _feed(runner, [better, first])

    assert message is not None
    assert "recordes" in message
    assert "7.0 km" in message
    assert "mais rápido na faixa de 5-8" in message


def test_external_coach_athlete_still_gets_celebrated():

    runner = make_runner(external_coach=True)

    first = _run(1, 7, 10_000, 3.33, 1)

    _feed(runner, [first])

    second = _run(2, 7, 15_000, 3.33, 2)

    message = _feed(runner, [second, first])

    assert message is not None


def _seed(profile, activities, has_token=True):

    with (
        patch(f"{MODULE}.TokenStore") as mock_token_store,
        patch(f"{MODULE}.StravaClient") as mock_client_cls,
    ):

        mock_token_store.return_value.load.return_value = (
            {"access_token": "x"} if has_token else None
        )

        mock_client_cls.return_value.get_last_activities = AsyncMock(
            return_value=activities,
        )

        asyncio.run(PersonalRecordDetector.seed(profile))


def test_seed_establishes_baseline_from_real_strava_history_immediately():
    """Conectar o Strava (onboarding/late connector) já estabelece a base —
    sem precisar esperar o primeiro treino processado pelo RunMind."""

    past = [_run(1, 7, 10_000, 3.33, 1)]

    _seed("novo_atleta", past)

    from app.infrastructure.persistence.personal_record_repository import (
        PersonalRecordRepository,
    )

    records = PersonalRecordRepository().load("novo_atleta")

    assert records["seeded"] is True
    assert records["longest_km"] == 10.0


def test_seed_without_strava_connected_does_nothing():

    _seed("sem_strava", [], has_token=False)

    from app.infrastructure.persistence.personal_record_repository import (
        PersonalRecordRepository,
    )

    assert PersonalRecordRepository().load("sem_strava") == {}


def test_seed_does_not_overwrite_an_already_seeded_athlete():
    """Reconexão do Strava não pode resetar uma base que já evoluiu além
    da semente inicial (senão perderia recordes já conquistados)."""

    first = _run(1, 7, 10_000, 3.33, 1)

    _seed("atleta", [first])

    # evolui a base (bate um recorde de verdade)
    second = _run(2, 7, 15_000, 3.33, 2)

    runner = make_runner(id="atleta")

    _feed(runner, [second, first])

    # reconectar o Strava não pode sobrescrever com uma semente mais curta
    _seed("atleta", [first])

    from app.infrastructure.persistence.personal_record_repository import (
        PersonalRecordRepository,
    )

    assert PersonalRecordRepository().load("atleta")["longest_km"] == 15.0


def test_seeding_first_means_first_real_run_can_already_celebrate():
    """O ponto principal: semeando na conexão (não no primeiro treino), o
    PRIMEIRO treino de verdade do atleta já pode comemorar, em vez de ser
    sempre 'gasto' só estabelecendo a base."""

    past = [_run(1, 7, 10_000, 3.33, 1)]

    _seed("atleta_novo", past)

    runner = make_runner(id="atleta_novo")

    first_real_run = _run(2, 7, 15_000, 3.33, 2)

    message = _feed(runner, [first_real_run, *past])

    assert message is not None
    assert "15.0 km" in message


def test_seed_dates_each_best_with_the_real_activity_date():
    """A semente usa a data REAL da atividade que detém o recorde — não a
    data de hoje — pra o recap mensal saber corretamente de qual mês é."""

    old_longest = _run(3, 5, 10_000, 3.33, 1)  # 3 de maio

    _seed("atleta_datado", [old_longest])

    records = PersonalRecordRepository().load("atleta_datado")

    assert records["longest_km_date"] == "2026-05-03"
    assert records["pace_by_band_dates"]["8-12"] == "2026-05-03"

    # marco de km acumulado é cumulativo, sem "dono" de uma atividade só —
    # o seed não data (evita atribuir errado a um mês)
    assert "total_km_milestone_date" not in records


def test_after_feedback_dates_wins_with_the_current_run_date():

    runner = make_runner()

    first = _run(1, 7, 10_000, 3.33, 1)

    _feed(runner, [first])  # semeia

    second = _run(15, 7, 15_000, 3.33, 2)  # 15 de julho

    _feed(runner, [second, first])

    records = PersonalRecordRepository().load(runner.id)

    assert records["longest_km_date"] == "2026-07-15"


def test_km_milestone_is_dated_only_on_the_live_path():

    runner = make_runner()

    base = [_run(d, 6, 9_000, 3.0, d) for d in range(1, 11)]  # 90km, sem cruzar marco

    _feed(runner, list(reversed(base)))  # semeia

    today = _run(1, 7, 15_000, 3.0, 100)  # cruza 100km AO VIVO

    _feed(runner, [today] + list(reversed(base)))

    records = PersonalRecordRepository().load(runner.id)

    assert records["total_km_milestone_date"] == "2026-07-01"
