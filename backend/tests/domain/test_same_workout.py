"""A regra única de "é o MESMO treino?" (Garmin + Strava). Caso real — Fernanda,
16/10: o Limiar de 5,38 km veio do Garmin (1674 s) e do Strava (1807 s, pausa
automática diferente) com o MESMO horário de início; a tolerância de 2% no tempo
não juntou os dois, o treino contou 2× e o resumo de domingo mostrou 35,8 km em
vez de 30,4. 8 pares assim na Fernanda e 5 no Maurício desde agosto."""

from datetime import UTC, datetime, timedelta

from app.application.use_cases.load_training_history import LoadTrainingHistory
from app.domain.same_workout import is_same_workout
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from tests.coach.factories import make_activity

START = datetime(2026, 10, 16, 19, 40, 34, tzinfo=UTC)


def _run(id, start=START, distance=5380.0, moving_time=1674, **kw):

    return make_activity(
        id=id, start_date=start, distance=distance, moving_time=moving_time, **kw,
    )


def test_same_start_and_distance_is_the_same_workout_even_if_moving_time_differs():
    """O caso real: 1674 s × 1807 s = 7,4% de diferença no tempo em movimento."""

    garmin = _run(24750100754, moving_time=1674)
    strava = _run(20614227793, moving_time=1807)

    assert is_same_workout(garmin, strava)
    assert is_same_workout(strava, garmin)


def test_walks_and_treadmill_copies_also_collapse():

    a = _run(1, distance=2310.0, moving_time=1502, sport="Walk")
    b = _run(2, distance=2310.0, moving_time=1629, sport="Walk")

    assert is_same_workout(a, b)


def test_start_a_few_seconds_apart_still_counts():

    assert is_same_workout(
        _run(1), _run(2, start=START + timedelta(seconds=45), moving_time=1800),
    )


def test_different_distance_at_the_same_start_is_not_the_same():

    assert not is_same_workout(_run(1, distance=5000.0), _run(2, distance=7000.0))


def test_two_real_runs_the_same_day_stay_apart():
    """Manhã e noite, distâncias parecidas e tempos diferentes: são dois treinos."""

    morning = _run(1, start=START.replace(hour=7), moving_time=1674)
    evening = _run(2, start=START.replace(hour=19), moving_time=1807)

    assert not is_same_workout(morning, evening)


def test_offset_copies_still_use_the_tight_same_day_rule():
    """Cópia com ~3 h de offset (transição de fonte): continua precisando de
    distância 0,5% + tempo 2% — a regra antiga, intacta."""

    base = _run(1, moving_time=1674)

    tight = _run(2, start=START + timedelta(hours=3), moving_time=1680)
    loose = _run(3, start=START + timedelta(hours=3), moving_time=1807)

    assert is_same_workout(base, tight)
    assert not is_same_workout(base, loose)


def test_naive_and_aware_datetimes_do_not_crash():

    naive = _run(1, start=START.replace(tzinfo=None))

    assert is_same_workout(naive, _run(2, moving_time=1807)) is False


def test_zero_distance_activities_do_not_merge_on_start_alone():

    a = _run(1, distance=0.0, moving_time=600)
    b = _run(2, distance=0.0, moving_time=1200)

    assert not is_same_workout(a, b)


def test_archive_and_history_share_the_rule():
    """As duas pontas (arquivo e histórico de treino) colapsam o mesmo par."""

    garmin = _run(24750100754, moving_time=1674)
    strava = _run(20614227793, moving_time=1807)

    assert len(ActivityArchiveRepository._dedup_runs([garmin, strava])) == 1
    assert len(LoadTrainingHistory._dedup([garmin, strava])) == 1


def test_archive_keeps_the_copy_with_zones_when_times_differ(tmp_path):

    repo = ActivityArchiveRepository()

    repo.storage = tmp_path

    strava = _run(20614227793, moving_time=1807, hr_zone_minutes=None)
    garmin = _run(24750100754, moving_time=1674, hr_zone_minutes=[0, 0, 10, 15, 3])

    repo.upsert_many("fernanda", [strava, garmin])

    kept = repo.load_activities("fernanda")

    assert len(kept) == 1
    assert kept[0].hr_zone_minutes == [0, 0, 10, 15, 3]
