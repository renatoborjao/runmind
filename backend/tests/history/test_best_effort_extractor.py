from app.application.history.best_effort_extractor import (
    BestEffortExtractor,
)
from app.application.history.best_effort_vdot import BestEffortVdot
from app.application.history.vdot_calculator import VdotCalculator


def _steady(pace_s_per_km: float, meters: int, step_s: float = 1.0):
    """Streams (distance, time) de uma corrida em ritmo constante — 1 amostra
    a cada `step_s` segundos até cobrir `meters`."""

    speed = 1000.0 / pace_s_per_km  # m/s

    distance = []

    time = []

    t = 0.0

    d = 0.0

    while d <= meters:

        distance.append(d)

        time.append(t)

        t += step_s

        d += speed * step_s

    return distance, time


def test_fastest_window_matches_steady_pace():
    """Ritmo constante 5:00/km por 6 km → a janela de 5k volta ~5:00/km."""

    distance, time = _steady(300, 6000)  # 300 s/km = 5:00/km

    efforts = BestEffortExtractor.efforts(distance, time)

    by_target = {round(e["distance"] / 1000): e for e in efforts}

    five_k = by_target[5]

    pace = five_k["elapsed_time"] / (five_k["distance"] / 1000)

    assert abs(pace - 300) < 3  # ~5:00/km, folga de amostragem


def test_captures_the_fast_surge_inside_an_easy_run():
    """O pulo do gato: um trecho FORTE de 3 km no meio de uma rodagem lenta é
    capturado — é o teto que a MÉDIA da corrida diluiria."""

    # 2 km leves (6:30/km) + 3 km fortes (4:10/km) + 2 km leves (6:30/km)
    d1, t1 = _steady(390, 2000)

    d2, t2 = _steady(250, 3000)

    d3, t3 = _steady(390, 2000)

    distance = list(d1)

    time = list(t1)

    for seq_d, seq_t in ((d2, t2), (d3, t3)):

        base_d = distance[-1]

        base_t = time[-1]

        for d, t in zip(seq_d, seq_t):

            distance.append(base_d + d)

            time.append(base_t + t)

    efforts = BestEffortExtractor.efforts(distance, time)

    three_k = next(e for e in efforts if round(e["distance"] / 1000) == 3)

    pace = three_k["elapsed_time"] / (three_k["distance"] / 1000)

    # pega o bloco forte (~4:10/km), não a média da rodagem
    assert pace < 270  # < 4:30/km

    # e o VDOT contínuo reflete o esforço forte, não a média
    vdot = BestEffortVdot.from_efforts(efforts)

    assert vdot > VdotCalculator.vdot(7000, 7000 / 1000 * 350)  # bem acima da média


def test_handles_non_uniform_sampling():
    """Amostragem a cada 3 s (device que faz downsample) — o tempo real de cada
    amostra é usado, então o pace sai certo (não supõe 1s)."""

    distance, time = _steady(300, 6000, step_s=3.0)

    efforts = BestEffortExtractor.efforts(distance, time)

    five_k = next(e for e in efforts if round(e["distance"] / 1000) == 5)

    pace = five_k["elapsed_time"] / (five_k["distance"] / 1000)

    assert abs(pace - 300) < 5


def test_short_run_yields_no_sustained_window():
    """Corrida de 1 km não gera janela ≥ 1600m — nada a ancorar."""

    distance, time = _steady(300, 1000)

    assert BestEffortExtractor.efforts(distance, time) == []


def test_ignores_none_and_backwards_samples():
    """Buracos (None) e recuos de distância (jitter) não quebram nem inflam."""

    distance, time = _steady(300, 4000)

    # injeta um buraco e um recuo
    distance[10] = None

    distance[20] = distance[19] - 50  # recuo de GPS

    efforts = BestEffortExtractor.efforts(distance, time)

    two_k = next(e for e in efforts if round(e["distance"] / 1000) == 2)

    pace = two_k["elapsed_time"] / (two_k["distance"] / 1000)

    assert 280 < pace < 320  # ~5:00/km, sem inflar pelo recuo


def test_empty_streams():

    assert BestEffortExtractor.efforts([], []) == []

    assert BestEffortExtractor.efforts([100], [1]) == []
