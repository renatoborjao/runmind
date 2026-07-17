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
    newest-first, como a API do Strava devolve de verdade."""

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


def test_km_milestone_crossed_triggers_once():

    runner = make_runner()

    # histórico com 90km acumulados antes do treino de hoje
    base = [
        _run(d, 6, 9_000, 3.0, d) for d in range(1, 11)
    ]

    _feed(runner, list(reversed(base)))  # semeia com 90km (nenhum marco)

    today = _run(1, 7, 15_000, 3.0, 100)  # empurra pra 105km -> cruza 100

    message = _feed(runner, [today] + list(reversed(base)))

    assert message is not None
    assert "100 km" in message

    # próximo treino comum não recruza o mesmo marco
    tomorrow = _run(2, 7, 5_000, 3.0, 101)

    again = _feed(
        runner, [tomorrow, today] + list(reversed(base)),
    )

    assert again is None or "100 km" not in again


def test_weekly_record_fires_once_per_week():

    runner = make_runner()

    # semana anterior: 20km (semente)
    seed_week = [_run(2, 6, 10_000, 3.0, 2), _run(1, 6, 10_000, 3.0, 1)]

    _feed(runner, seed_week)

    # nova semana (ISO diferente), primeiro treino já supera os 20km da
    # semana semeada
    week2_run1 = _run(6, 7, 25_000, 3.0, 3)  # segunda-feira

    first_message = _feed(runner, [week2_run1] + seed_week)

    assert first_message is not None
    assert "maior volume" in first_message

    # segundo treino NA MESMA semana (mesmo que aumente ainda mais o volume)
    # não repete a comemoração
    week2_run2 = _run(8, 7, 10_000, 3.0, 4)  # quarta-feira

    second_message = _feed(
        runner, [week2_run2, week2_run1] + seed_week,
    )

    assert second_message is None


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

    first = _run(1, 7, 10_000, 3.33, 1)

    _feed(runner, [first])  # semeia longest=10km, semana ~10km

    # semana seguinte, mesmo pace (sem PR de faixa) mas mais longa e com
    # mais km na semana -> bate corrida mais longa E semana de maior volume
    big = _run(8, 7, 11_500, 3.33, 2)

    message = _feed(runner, [big, first])

    assert message is not None
    assert "recordes" in message
    assert "11.5 km" in message
    assert "maior volume" in message


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
