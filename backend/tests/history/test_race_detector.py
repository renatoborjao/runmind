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


# --- o NOME de um treino não é prova (Leonardo, 21/10) -------------------------------------------


def test_the_coachs_own_race_pace_workout_is_not_a_race():
    """"Ritmind · Ritmo de Prova 8.0km" (09/10) virou "prova": o atleta ficou em modo pós-prova
    e o coach parou de puxar. Era um TREINO."""

    acts = [
        _Act(date(2026, 9, 3), name="Ritmind · Rodagem Leve"),
        _Act(date(2026, 9, 5), name="Ritmind · Ritmo de Prova 8.0km", distance=8000),
    ]

    assert RaceDetector.most_recent(acts, _TODAY) is None


def test_none_of_the_coachs_preparation_sessions_count_as_race():

    names = [
        "São Paulo - Ritmind · Ritmo de Prova 8.0km",   # com o prefixo de cidade do Garmin
        "Ritmind · Ativação Pré-Prova",
        "Ritmind · Soltura Pré-Prova 4.0km",
        "Ritmind · Simulado de 10k 8.0km",
        "Ritmind · Simulado / prova-teste",
        "RunMind · Ritmo de Prova",                      # o nome de antes do rebrand
    ]

    for name in names:

        assert RaceDetector.most_recent([_Act(date(2026, 9, 5), name=name)], _TODAY) is None, name


def test_the_coachs_race_day_session_is_still_the_race():
    """Só a sessão do DIA da prova ("Prova 10.0km") é a prova — o debrief ou o Strava podem não ter
    marcado, e a rede por nome precisa pegar."""

    for name in ("Ritmind · Prova 10.0km", "São Paulo - Ritmind · Prova 10.0km", "Ritmind · Prova"):

        race = RaceDetector.most_recent([_Act(date(2026, 8, 23), name=name)], _TODAY)

        assert race is not None and race.date == date(2026, 8, 23), name


def test_training_words_in_a_name_the_athlete_gave_are_not_a_race_either():

    for name in ("Simulado 10k", "ritmo de prova 6km", "Soltura pré-prova", "Simulado de prova 8k"):

        assert RaceDetector.most_recent([_Act(date(2026, 9, 5), name=name)], _TODAY) is None, name

    # mas "prova" sozinha, ou um evento, segue sendo prova
    for name in ("Prova 10k", "Meia Maratona"):

        assert RaceDetector.most_recent([_Act(date(2026, 9, 5), name=name)], _TODAY) is not None


def test_a_real_race_is_not_hidden_by_a_later_training_with_race_in_the_name():
    """O coach marcou a prova (Strava workout_type=1) e depois fez um "Ritmo de Prova": a última
    prova segue sendo a de verdade."""

    acts = [
        _Act(date(2026, 8, 23), name="Corrida", workout_type=1),
        _Act(date(2026, 9, 5), name="Ritmind · Ritmo de Prova 8.0km"),
    ]

    race = RaceDetector.most_recent(acts, _TODAY)

    assert race is not None and race.date == date(2026, 8, 23)


def test_the_strava_race_mark_wins_over_the_name():
    """O atleta marcou como prova no Strava: é prova, mesmo com nome de treino do coach."""

    acts = [_Act(date(2026, 9, 5), name="Ritmind · Ritmo de Prova 8.0km", workout_type=1)]

    race = RaceDetector.most_recent(acts, _TODAY)

    assert race is not None and race.date == date(2026, 9, 5)
