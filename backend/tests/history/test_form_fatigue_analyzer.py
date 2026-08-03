from app.application.history.form_fatigue_analyzer import FormFatigueAnalyzer


def test_detects_cadence_collapse_at_the_end():
    """Cadência alta no começo e desabando no fim (num treino longo) = fade."""

    cadence = [88] * 70 + [80] * 30  # ~176 spm -> ~160 spm

    assert FormFatigueAnalyzer.fades(cadence, distance=[7000]) is True


def test_no_fade_when_cadence_holds():

    assert FormFatigueAnalyzer.fades([85] * 100, distance=[7000]) is False


def test_short_run_is_not_evaluated():
    """Treino curto não tem fadiga de fim de longão — não avalia."""

    cadence = [88] * 70 + [80] * 30

    assert FormFatigueAnalyzer.fades(cadence, distance=[4000]) is False


def test_zero_samples_are_ignored():
    """Zeros (parado/sem dado) no começo não contam como cadência baixa."""

    cadence = [0] * 20 + [85] * 80

    assert FormFatigueAnalyzer.fades(cadence, distance=[7000]) is False


def test_too_few_samples_returns_false():

    assert FormFatigueAnalyzer.fades([85] * 10, distance=[7000]) is False
