from datetime import date, timedelta
from types import SimpleNamespace

from app.application.history.training_reality_analyzer import (
    ALIGNED,
    OVER,
    UNDER,
    TrainingRealityAnalyzer,
    frequency_reconcile_message,
    training_reality_directive,
)

_MONDAY = date(2026, 8, 3)  # uma segunda qualquer


def _acts(weekly_counts, km_each=6.0):
    """Gera atividades: uma lista de contagens por semana (antiga->recente),
    cada corrida com `km_each` km."""

    acts = []

    for w, n in enumerate(weekly_counts):

        week_monday = _MONDAY + timedelta(days=7 * w)

        for r in range(n):

            day = week_monday + timedelta(days=r)

            acts.append(
                SimpleNamespace(
                    start_date=day.isoformat(),
                    start_date_local=day.isoformat(),
                    distance=km_each * 1000,
                )
            )

    return acts


def test_routine_over_when_exceeds_in_majority_of_weeks():
    """Hélio: 4,4,3,4 nas últimas 4 -> 4x em 3 delas = rotina 'over'."""

    v = TrainingRealityAnalyzer.assess(3, _acts([4, 4, 3, 4]))

    assert v.verdict == OVER
    assert v.weeks_over == 3
    d = training_reality_directive(v)
    assert "MAIORIA" in d and "NÃO adicione dias" in d


def test_single_spike_is_not_routine():
    """Maurício: 2,4,6,3 -> um pico de 6, over só em 2 de 4 -> NÃO dispara."""

    v = TrainingRealityAnalyzer.assess(3, _acts([2, 4, 6, 3]))

    assert v.verdict == ALIGNED
    assert training_reality_directive(v) == ""


def test_aligned_when_hits_registered():

    v = TrainingRealityAnalyzer.assess(3, _acts([3, 3, 3, 3]))

    assert v.verdict == ALIGNED


def test_routine_under_when_below_in_majority():

    v = TrainingRealityAnalyzer.assess(4, _acts([2, 2, 3, 2]))

    assert v.verdict == UNDER
    assert "cumpre" in training_reality_directive(v)


def test_insufficient_weeks_never_asserts():
    """Menos de 4 semanas ativas: não dá pra afirmar rotina."""

    v = TrainingRealityAnalyzer.assess(3, _acts([4, 5, 4]))

    assert v.verdict == ALIGNED


def test_zero_registered_is_aligned():

    assert TrainingRealityAnalyzer.assess(0, _acts([4, 4, 4, 4])).verdict == ALIGNED


def test_only_last_four_weeks_count():
    """Semanas antigas de over não contam se as 4 recentes batem."""

    v = TrainingRealityAnalyzer.assess(3, _acts([5, 5, 3, 3, 3, 3]))

    assert v.verdict == ALIGNED  # as 4 últimas são 3,3,3,3


def test_frequency_message_asks_to_officialize_on_over():

    v = TrainingRealityAnalyzer.assess(3, _acts([4, 4, 3, 4]))

    msg = frequency_reconcile_message("Hélio", v)

    assert "4 dias" in msg and "Hélio" in msg


def test_frequency_message_empty_when_aligned():

    v = TrainingRealityAnalyzer.assess(3, _acts([3, 3, 3, 3]))

    assert frequency_reconcile_message("Hélio", v) == ""
