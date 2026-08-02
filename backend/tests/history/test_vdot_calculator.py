"""O VDOT e os ritmos batem com as tabelas publicadas do Daniels (a validação
externa do modelo — não é chute nosso, é a ciência de referência)."""

from app.application.history.vdot_calculator import (
    FRAC_INTERVAL,
    FRAC_MARATHON,
    FRAC_REP,
    FRAC_THRESHOLD,
    VdotCalculator,
)


def _pace_str(pace_min_km: float) -> str:

    m = int(pace_min_km)

    s = round((pace_min_km - m) * 60)

    if s == 60:

        m += 1
        s = 0

    return f"{m}:{s:02d}"


def test_vdot_from_5k_1957_is_about_50():
    """5000 m em 19:57 = VDOT 50 na tabela do Daniels."""

    v = VdotCalculator.vdot(5000, 19 * 60 + 57)

    assert abs(v - 50) < 0.5


def test_vdot_from_3k_10min_is_about_59():
    """3000 m em 10:00 ≈ VDOT 59 (esforço mais forte, VDOT maior)."""

    v = VdotCalculator.vdot(3000, 600)

    assert abs(v - 59) < 1.0


def test_training_paces_match_daniels_tables_for_vdot_50():
    """Pros ritmos de treino no VDOT 50, o Daniels publica (por km):
    limiar 4:15, maratona 4:30, intervalado 3:57, repetição 3:41."""

    assert _pace_str(VdotCalculator.pace_min_km(50, FRAC_THRESHOLD)) == "4:15"
    assert _pace_str(VdotCalculator.pace_min_km(50, FRAC_MARATHON)) == "4:30"
    assert _pace_str(VdotCalculator.pace_min_km(50, FRAC_INTERVAL)) == "3:55"
    assert _pace_str(VdotCalculator.pace_min_km(50, FRAC_REP)) == "3:41"


def test_paces_get_faster_with_higher_vdot():
    """Atleta mais em forma (VDOT maior) -> todo ritmo fica mais rápido."""

    slow = VdotCalculator.pace_min_km(45, FRAC_THRESHOLD)

    fast = VdotCalculator.pace_min_km(55, FRAC_THRESHOLD)

    assert fast < slow


def test_zone_order_easy_slower_than_threshold_slower_than_interval():
    """Fácil é mais lento (número maior) que limiar, que é mais lento que
    intervalado — a escala de intensidade em ordem."""

    easy = VdotCalculator.pace_min_km(50, 0.70)

    threshold = VdotCalculator.pace_min_km(50, FRAC_THRESHOLD)

    interval = VdotCalculator.pace_min_km(50, FRAC_INTERVAL)

    assert easy > threshold > interval


def test_non_positive_inputs_raise():

    for distance, seconds in ((0, 600), (5000, 0), (-1, 10)):

        try:

            VdotCalculator.vdot(distance, seconds)

            assert False, "deveria ter levantado ValueError"

        except ValueError:

            pass
