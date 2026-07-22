from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app.application.history.training_load_analyzer import (
    TrainingLoadAnalyzer,
)
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_load import (
    LOAD_DETRAINING,
    LOAD_HIGH,
    LOAD_INSUFFICIENT,
    LOAD_OPTIMAL,
)

REF = date(2026, 7, 22)


def _act(days_ago: int, minutes: int):
    """Atividade mínima: só o que o analisador usa (start_date + moving_time)."""

    day = REF - timedelta(days=days_ago)

    return SimpleNamespace(
        start_date=datetime(day.year, day.month, day.day, 10, 0),
        moving_time=minutes * 60,
    )


def _analyze(activities):

    return TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=activities),
        reference_date=REF,
    )


def test_optimal_when_load_is_steady():

    # 60 min/dia por 28 dias -> aguda = crônica -> ACWR ~1.0
    load = _analyze([_act(d, 60) for d in range(28)])

    assert load.acute_load == 420.0
    assert load.chronic_load == 420.0
    assert load.acwr == 1.0
    assert load.status == LOAD_OPTIMAL


def test_high_when_ramping_fast():

    # base fraca + pico nos últimos 7 dias -> ACWR bem acima de 1.5
    acts = [_act(27, 30)] + [_act(d, 60) for d in range(7)]

    load = _analyze(acts)

    assert load.acwr > 1.5
    assert load.status == LOAD_HIGH


def test_detraining_when_acute_drops():

    # carregou 21 dias e parou na última semana -> aguda 0 -> ACWR 0
    load = _analyze([_act(d, 60) for d in range(7, 28)])

    assert load.acute_load == 0.0
    assert load.acwr == 0.0
    assert load.status == LOAD_DETRAINING


def test_insufficient_history_overrides_ratio():

    # só 5 dias de histórico: mesmo com ACWR alto, não arrisca veredito
    load = _analyze([_act(d, 60) for d in range(5)])

    assert load.days_of_history == 5
    assert load.status == LOAD_INSUFFICIENT


def test_weekly_loads_ordered_old_to_new():

    acts = [_act(0, 10), _act(7, 20), _act(14, 30), _act(21, 40)]

    load = _analyze(acts)

    assert load.weekly_loads == [40.0, 30.0, 20.0, 10.0]


def _hr_act(days_ago: int, minutes: int, hr):

    day = REF - timedelta(days=days_ago)

    return SimpleNamespace(
        start_date=datetime(day.year, day.month, day.day, 10, 0),
        moving_time=minutes * 60,
        average_heartrate=hr,
    )


# ---------------- v2: intensidade (duração × %FCR) ----------------


def test_intensity_weights_hard_sessions_more_than_easy():

    hard = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=[_hr_act(0, 60, 160)]),
        reference_date=REF,
        resting_hr=60,
        max_hr=180,
    )

    easy = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=[_hr_act(0, 60, 100)]),
        reference_date=REF,
        resting_hr=60,
        max_hr=180,
    )

    # mesma duração, FC maior -> mais carga
    assert hard.acute_load > easy.acute_load
    # hrr 160: (160-60)/(180-60)=0.833 -> 60*0.833 ~= 50
    assert hard.acute_load == 50.0


def test_without_hr_params_stays_duration_only():

    # sem FC repouso/máx: v1 (duração), ignora a FC da atividade
    load = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=[_hr_act(0, 60, 160)]),
        reference_date=REF,
    )

    assert load.acute_load == 60.0


def test_session_without_hr_uses_median_factor():

    # 2 sessões com FC (fatores 1.0 e 0.0 -> mediana 0.5) + 1 sem FC de 100min
    acts = [
        _hr_act(0, 60, 180),   # hrr 1.0
        _hr_act(1, 60, 60),    # hrr 0.0
        _hr_act(2, 100, None),  # sem FC -> mediana 0.5 -> 50
    ]

    load = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=acts),
        reference_date=REF,
        resting_hr=60,
        max_hr=180,
    )

    # 60*1.0 + 60*0.0 + 100*0.5 = 110
    assert load.acute_load == 110.0


def test_banister_weights_hard_effort_more_than_linear():

    # com sexo, a exponencial de Banister pesa o esforço forte muito mais que
    # o %FCR linear (sem sexo)
    linear = TrainingLoadAnalyzer._intensity_factor(0.85, None)

    banister = TrainingLoadAnalyzer._intensity_factor(0.85, "M")

    assert linear == 0.85
    assert banister > linear


def test_banister_differs_by_sex():

    male = TrainingLoadAnalyzer._intensity_factor(0.8, "M")

    female = TrainingLoadAnalyzer._intensity_factor(0.8, "F")

    assert male != female


def test_sex_word_is_normalized():

    # onboarding pode gravar "masculino"/"feminino" — normaliza pela inicial
    assert (
        TrainingLoadAnalyzer._intensity_factor(0.7, "masculino")
        == TrainingLoadAnalyzer._intensity_factor(0.7, "M")
    )

    assert (
        TrainingLoadAnalyzer._intensity_factor(0.7, "feminino")
        == TrainingLoadAnalyzer._intensity_factor(0.7, "F")
    )


def test_invalid_max_hr_falls_back_to_duration():

    # FC máx <= repouso (dado torto): não pondera, cai na duração
    load = TrainingLoadAnalyzer.analyze(
        TrainingHistory(activities=[_hr_act(0, 60, 160)]),
        reference_date=REF,
        resting_hr=180,
        max_hr=170,
    )

    assert load.acute_load == 60.0


def test_empty_history_is_insufficient():

    load = _analyze([])

    assert load.acute_load == 0.0
    assert load.chronic_load == 0.0
    assert load.acwr is None
    assert load.status == LOAD_INSUFFICIENT
    assert load.days_of_history == 0
    assert load.weekly_loads == [0.0, 0.0, 0.0, 0.0]
