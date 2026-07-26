from datetime import date, datetime, timedelta

from app.application.history.aerobic_efficiency_analyzer import (
    AerobicEfficiencyAnalyzer,
)
from app.domain.entities.aerobic_efficiency import (
    EFF_DECLINING,
    EFF_IMPROVING,
    EFF_INSUFFICIENT,
    EFF_STABLE,
)
from tests.coach.factories import make_activity

REF = date(2026, 7, 25)

# renato2: FC repouso ~60, FC máx ~180 (idade ~40) -> faixa aeróbica ampla
RESTING = 60
MAXHR = 180


def _run(days_ago: int, *, speed: float, hr: float, km: float = 8.0):

    start = datetime.combine(
        REF - timedelta(days=days_ago), datetime.min.time()
    ).replace(hour=7)

    return make_activity(
        id=days_ago,
        start_date=start,
        distance=km * 1000,
        average_speed=speed,
        average_heartrate=hr,
    )


def _analyze(activities):

    return AerobicEfficiencyAnalyzer.analyze(
        activities, reference_date=REF, resting_hr=RESTING, max_hr=MAXHR,
    )


def test_insufficient_when_few_runs():

    runs = [_run(d, speed=2.6, hr=150) for d in (5, 12, 19)]

    result = _analyze(runs)

    assert result.direction == EFF_INSUFFICIENT
    assert result.runs_counted == 3
    assert result.has_data is False


def test_detects_improving_fitness():
    """Mesma FC (150) mas ficando mais rápido nas corridas recentes -> corpo
    mais econômico -> eficiência SUBINDO."""

    earlier = [_run(d, speed=2.55, hr=150) for d in (55, 50, 45)]

    recent = [_run(d, speed=2.75, hr=150) for d in (15, 10, 5)]

    result = _analyze(earlier + recent)

    assert result.direction == EFF_IMPROVING
    assert result.runs_counted == 6
    assert result.improving is True
    # na mesma FC, o pace recente é mais rápido -> ganho positivo
    assert result.pace_gain_sec > 0
    # ganho modesto (recreativo): NÃO bate no teto de credibilidade
    assert result.pace_gain_capped is False


def test_cap_clamps_magnitude_and_flags():

    assert AerobicEfficiencyAnalyzer._cap(105, 40) == (40, True)
    assert AerobicEfficiencyAnalyzer._cap(-105, 40) == (-40, True)
    assert AerobicEfficiencyAnalyzer._cap(20, 40) == (20, False)
    assert AerobicEfficiencyAnalyzer._cap(None, 40) == (None, False)


def test_beginner_ramp_pace_gain_is_capped():
    """Rampa dramática de iniciante (quase trote -> corrida): o ganho é REAL
    porém incrível (>1min/km). É limitado ao teto e marcado -> o writer dirá
    'mais de X' em vez de cuspir um número que soa como bug."""

    earlier = [_run(d, speed=2.05, hr=150) for d in (55, 50, 45)]

    recent = [_run(d, speed=3.15, hr=150) for d in (15, 10, 5)]

    result = _analyze(earlier + recent)

    assert result.direction == EFF_IMPROVING
    assert result.pace_gain_capped is True
    assert result.pace_gain_sec == 40    # teto


def test_detects_declining_fitness():
    """Mesma FC mas ficando mais LENTO -> eficiência caindo (sinal de algo
    pesando: calor, fadiga acumulada, destreino)."""

    earlier = [_run(d, speed=2.75, hr=150) for d in (55, 50, 45)]

    recent = [_run(d, speed=2.55, hr=150) for d in (15, 10, 5)]

    result = _analyze(earlier + recent)

    assert result.direction == EFF_DECLINING
    assert result.pace_gain_sec < 0


def test_stable_within_noise():
    """Variação minúscula de EF fica em ESTÁVEL (não vira falso alarme)."""

    earlier = [_run(d, speed=2.60, hr=150) for d in (55, 50, 45)]

    recent = [_run(d, speed=2.61, hr=150) for d in (15, 10, 5)]

    result = _analyze(earlier + recent)

    assert result.direction == EFF_STABLE


def test_same_pace_lower_hr_is_improving():
    """Mesmo pace, FC caindo -> também é ganho de eficiência, e a tradução
    'no mesmo pace, FC caiu X bpm' fica positiva."""

    earlier = [_run(d, speed=2.65, hr=152) for d in (55, 50, 45)]

    recent = [_run(d, speed=2.65, hr=142) for d in (15, 10, 5)]

    result = _analyze(earlier + recent)

    assert result.direction == EFF_IMPROVING
    assert result.hr_drop_bpm > 0


def test_walks_and_hard_efforts_are_excluded():
    """Caminhada (FCR baixa) e prova/tiro (FCR alta) não entram — economia não
    comparável a rodagem aeróbica. Sobram só as 6 corridas EASY, que decidem."""

    aerobic = (
        [_run(d, speed=2.55, hr=150) for d in (55, 50, 45)]
        + [_run(d, speed=2.75, hr=150) for d in (15, 10, 5)]
    )

    # FCR ~0.17 (caminhada) e ~0.92 (all-out): fora da faixa [0.45, 0.80]
    walk = _run(30, speed=1.6, hr=80, km=5.0)

    allout = _run(20, speed=3.4, hr=170, km=10.0)

    result = _analyze(aerobic + [walk, allout])

    assert result.runs_counted == 6
    assert result.direction == EFF_IMPROVING


def test_short_runs_are_ignored():
    """Corrida abaixo de 3 km é ruído e não conta."""

    aerobic = (
        [_run(d, speed=2.55, hr=150) for d in (55, 50, 45)]
        + [_run(d, speed=2.75, hr=150) for d in (15, 10, 5)]
    )

    short = _run(25, speed=2.6, hr=150, km=1.5)

    result = _analyze(aerobic + [short])

    assert result.runs_counted == 6


def test_runs_outside_window_are_ignored():
    """Corrida além da janela de 8 semanas fica de fora."""

    aerobic = (
        [_run(d, speed=2.55, hr=150) for d in (55, 50, 45)]
        + [_run(d, speed=2.75, hr=150) for d in (15, 10, 5)]
    )

    ancient = _run(200, speed=2.0, hr=150, km=8.0)

    result = _analyze(aerobic + [ancient])

    assert result.runs_counted == 6


def test_without_hr_bounds_still_trends_on_runs_with_hr():
    """Sem FC repouso/máx (não dá pra estimar %FCR), não filtra por faixa mas
    ainda calcula a tendência com as corridas que têm FC."""

    earlier = [_run(d, speed=2.55, hr=150) for d in (55, 50, 45)]

    recent = [_run(d, speed=2.75, hr=150) for d in (15, 10, 5)]

    result = AerobicEfficiencyAnalyzer.analyze(
        earlier + recent, reference_date=REF,
    )

    assert result.direction == EFF_IMPROVING
    assert result.runs_counted == 6
