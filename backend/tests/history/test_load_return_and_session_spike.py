"""RETORNO AO PLATÔ e SALTO DE SESSÃO (Renato, 08/11). Depois de semanas de 91-128 min (gripe, pausa
médica), a semana de 195 min (3 corridas, maior de 15,5 km) deu ACWR 1,42 e o corpo ficou
"sobrecarregado" — mas o maior treino ficou só 3% acima do maior dos 30 dias anteriores e a semana
dobrou porque ele VOLTOU a 3 corridas. A razão semanal e o passo de volume são preditores fracos
de lesão (Impellizzeri 2020; Frandsen/BJSM 2025); o salto de UMA corrida é o que importa."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app.application.history.training_load_analyzer import TrainingLoadAnalyzer
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_load import LOAD_CAUTION, LOAD_HIGH, LOAD_OPTIMAL

REF = date(2026, 11, 8)


def _run(days_ago: int, minutes: float, km: float):

    day = REF - timedelta(days=days_ago)

    return SimpleNamespace(
        start_date=datetime(day.year, day.month, day.day, 7, 0),
        moving_time=minutes * 60,
        distance=km * 1000,
        hr_zone_minutes=None, hr_histogram=None, average_heartrate=None,
    )


def _history(weeks_back: dict[int, list[tuple[float, float]]]):
    """`weeks_back[w]` = corridas (min, km) da semana que fechou `w` semanas antes de REF."""

    acts = []

    for w, runs in weeks_back.items():

        for index, (minutes, km) in enumerate(runs):

            acts.append(_run(7 * w + 1 + index, minutes, km))

    return TrainingHistory(activities=acts)


# o platô de agosto-setembro (4 semanas de ~180 min, 28-31 km), uma parada, e a volta lenta
RENATO = {
    9: [(70, 10.7), (60, 9.0), (42, 8.2)],
    8: [(75, 12.0), (60, 9.0), (58, 10.0)],
    7: [(70, 11.0), (55, 9.0), (63, 8.6)],
    6: [(73, 13.4), (60, 9.0), (55, 7.9)],
    # semana 5: parada médica / gripe
    4: [(93, 15.0)],
    3: [(85, 14.0), (43, 7.1)],
    2: [(65, 10.0), (47, 7.7)],
    1: [(91, 14.7)],
    0: [(100, 15.5), (50, 8.0), (45, 7.0)],
}


def _analyze(weeks):

    return TrainingLoadAnalyzer.analyze(_history(weeks), reference_date=REF)


def test_the_longest_run_of_the_week_is_compared_to_the_longest_of_the_30_days_before():

    load = _analyze(RENATO)

    assert load.long_run_km == (15.5, 15.0)
    assert load.long_spike == 0.033


def test_going_back_to_three_runs_with_no_session_spike_is_a_return_not_an_overload():
    """A semana dobrou (91 → 195 min) mas nenhuma corrida foi um salto: é retorno ao platô."""

    load = _analyze(RENATO)

    assert load.rebound is not None
    assert load.status == LOAD_OPTIMAL and load.acwr < 1.2


def test_the_same_week_with_a_session_spike_stays_a_spike():
    """Se o longão de 15,5 fosse de 20 km (+33% sobre o maior dos 30 dias), a semana segue sendo
    sinal de carga — o salto de sessão é justamente o que NÃO se libera."""

    spiked = dict(RENATO)

    spiked[0] = [(135, 20.0), (50, 8.0), (45, 7.0)]

    load = _analyze(spiked)

    assert load.long_spike is not None and load.long_spike > 0.30
    assert load.rebound is None
    assert load.status in (LOAD_CAUTION, LOAD_HIGH)


def test_without_a_run_in_the_30_days_before_there_is_no_spike_to_state():

    load = _analyze({0: [(100, 15.5), (50, 8.0)]})

    assert load.long_spike is None and load.long_run_km is None


def test_the_average_of_the_best_weeks_does_not_make_the_best_week_a_spike():
    """O sustentado é a MÉDIA das melhores semanas (183): a melhor semana dele (193) fica acima
    dela, e voltar a ela não é pico — tolerância de 10% sobre o sustentado."""

    load = _analyze(RENATO)

    assert load.rebound is not None
    sustained, acute = load.rebound

    assert acute > sustained and acute <= 1.10 * sustained
