from app.application.history.interval_analyzer import IntervalAnalyzer


def _stream():
    """Monta um stream sintético: aquecimento longo + 8 tiros (~240 m a
    ~3 m/s) separados por recuperação (~1.6 m/s), com FC subindo no tiro
    e caindo na pausa."""

    vel = []
    hr = []

    # aquecimento: 300 s contínuos (>700 m => não conta como tiro)
    vel += [2.9] * 300
    hr += list(range(110, 160)) + [160] * 250

    # trote/pausa entre aquecimento e o 1º tiro (como no treino real)
    vel += [1.6] * 100
    hr += [150] * 100

    for _ in range(8):

        # tiro: 80 s a 3.0 m/s (~240 m)
        vel += [3.0] * 80
        hr += [170] * 80

        # recuperação: 100 s a 1.6 m/s
        vel += [1.6] * 100
        hr += [145] * 100

    # distância acumulada coerente com a velocidade
    distance = []
    acc = 0.0
    for v in vel:
        acc += v
        distance.append(acc)

    return vel, hr, distance


def test_detects_eight_reps_with_hr_response():

    vel, hr, distance = _stream()

    analysis = IntervalAnalyzer.analyze(vel, hr, distance)

    assert analysis is not None
    assert analysis.rep_count == 8
    assert analysis.avg_peak_hr == 170
    assert analysis.avg_recovery_hr == 145
    # pace do tiro ~ 3 m/s => ~5.56 min/km
    assert 5.4 <= analysis.avg_rep_pace <= 5.7


def test_run_walk_is_not_interval():
    """Corrida-caminhada oscila a velocidade, mas os trechos de corrida não
    são tiro: pace perto da média e FC quase sem variação. Não é intervalado
    (bug real do Mauricio)."""

    vel = []
    hr = []

    # aquecimento contínuo (>700 m => não conta como tiro)
    vel += [2.6] * 300
    hr += [140] * 300

    for _ in range(4):

        # "corrida": levemente mais rápida, FC 150
        vel += [2.6] * 110
        hr += [150] * 110

        # "caminhada": mais lenta, FC mal cai (147)
        vel += [1.9] * 90
        hr += [147] * 90

    distance = []
    acc = 0.0
    for v in vel:
        acc += v
        distance.append(acc)

    # FC quase sem swing (3 bpm) e pace dos trechos perto da média => None
    assert IntervalAnalyzer.analyze(vel, hr, distance) is None


def test_steady_run_has_no_interval():

    vel = [2.8] * 1800
    distance = []
    acc = 0.0
    for v in vel:
        acc += v
        distance.append(acc)

    assert IntervalAnalyzer.analyze(vel, [150] * 1800, distance) is None


def test_no_stream_returns_none():

    assert IntervalAnalyzer.analyze([], [], []) is None
