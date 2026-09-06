from datetime import date, datetime

from app.application.history.race_detector import RaceDetector


class _Act:
    """Atividade mínima (só o que o detector lê)."""

    def __init__(self, day, name="Corrida matinal", sport="Run",
                 distance=10000, workout_type=None):
        self.start_date = datetime(day.year, day.month, day.day, 7, 0)
        self.name = name
        self.sport = sport
        self.distance = distance
        self.raw = {} if workout_type is None else {"workout_type": workout_type}


_TODAY = date(2026, 9, 7)


def test_detects_race_by_strava_workout_type():
    acts = [
        _Act(date(2026, 8, 23), name="Corrida", workout_type=1),
        _Act(date(2026, 9, 1), name="Rodagem leve"),
    ]

    race = RaceDetector.most_recent(acts, _TODAY)

    assert race is not None
    assert race.date == date(2026, 8, 23)
    assert race.weeks_ago == 2


def test_detects_race_by_name_when_unmarked():
    acts = [
        _Act(date(2026, 8, 23), name="Track&Field Run Series - Villa-Lobos"),
    ]

    race = RaceDetector.most_recent(acts, _TODAY)

    assert race is not None
    assert race.weeks_ago == 2


def test_plain_runs_are_not_races():
    acts = [
        _Act(date(2026, 9, 1), name="Corrida matinal"),
        _Act(date(2026, 9, 3), name="Longão de domingo"),
    ]

    assert RaceDetector.most_recent(acts, _TODAY) is None


def test_picks_most_recent_race():
    acts = [
        _Act(date(2026, 7, 5), name="Meia Maratona"),
        _Act(date(2026, 8, 23), name="Prova 10k", workout_type=1),
    ]

    race = RaceDetector.most_recent(acts, _TODAY)

    assert race.date == date(2026, 8, 23)


def test_ignores_races_outside_lookback():
    acts = [_Act(date(2026, 1, 10), name="Maratona", workout_type=1)]

    assert RaceDetector.most_recent(acts, _TODAY) is None


def test_uses_first_party_race_result_without_strava_tag():
    """Fonte de PRIMEIRA-MÃO: a prova que o coach já debriefou é reconhecida
    mesmo sem marcação no Strava (bug do Renato: 'Netshoes Run 10K' não estava
    marcada como prova, mas o coach tinha o resultado gravado)."""

    acts = [_Act(date(2026, 8, 23), name="Netshoes Run 10K")]  # sem workout_type
    results = [{"date": "2026-08-23", "distance_km": 10.03,
                "race_label": "10 km", "time": "54:18", "beat": True}]

    # sem os resultados, a atividade crua não é reconhecida como prova
    assert RaceDetector.most_recent(acts, _TODAY) is None

    # com o registro do coach, é reconhecida (autoritativa)
    race = RaceDetector.most_recent(acts, _TODAY, past_results=results)

    assert race is not None
    assert race.date == date(2026, 8, 23)
    assert race.weeks_ago == 2
    assert race.distance_km == 10.03


def test_ignores_non_run_race():
    acts = [_Act(date(2026, 8, 23), name="Prova de ciclismo",
                 sport="Ride", workout_type=1)]

    assert RaceDetector.most_recent(acts, _TODAY) is None


def test_empty_history_is_safe():
    assert RaceDetector.most_recent([], _TODAY) is None
    assert RaceDetector.most_recent(None, _TODAY) is None
