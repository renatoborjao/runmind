"""ENTREGOU o plano? A semana fechada mais recente saiu >= 90% do prescrito E ele não vem de
não-entrega (mediana das últimas semanas acima do piso). É o que separa "sinal curto de corpo num
atleta que absorve" (segurar a rampa) de "ele não está dando conta" (ancorar no que cumpre).
Renato 08/11: 30,5 km contra 30 prescritos, longão de 15,5 km feito."""

from datetime import date, timedelta
from types import SimpleNamespace

from app.application.coach.context.athlete_dossier import AthleteDossier


def _week(index, planned, done, long_km=0.0, in_progress=False):

    return SimpleNamespace(
        week_start=date(2026, 10, 5) + timedelta(weeks=index),
        in_progress=in_progress, planned_km=planned, done_km=done, done_long_km=long_km,
        planned_sessions=3, done_runs=3, fulfilled=3, missed=[], pending=[], extras=0,
        phase="BASE", objective="", deload=False, planned_long_km=0.0, planned_key=[],
        prev_done_km=0.0, quality_done_km=0.0, route_km=None, route_note=None,
    )


def _data(weeks):

    data = SimpleNamespace(profile="renato2")
    data.weeks = weeks

    return data


def _with_ledger(monkeypatch, weeks):

    monkeypatch.setattr(AthleteDossier, "_ledger", staticmethod(lambda data: data.weeks))

    return _data(weeks)


def test_a_full_last_week_after_steady_delivery_is_delivering(monkeypatch):

    data = _with_ledger(monkeypatch, [
        _week(0, 25, 26), _week(1, 25, 24), _week(2, 30, 30.5, 15.5),
        _week(3, 25, 0, in_progress=True),
    ])

    assert AthleteDossier._is_delivering(data) is True


def test_a_week_that_closed_below_ninety_percent_is_not(monkeypatch):

    data = _with_ledger(monkeypatch, [_week(0, 25, 26), _week(1, 25, 25), _week(2, 30, 24)])

    assert AthleteDossier._is_delivering(data) is False


def test_a_history_of_not_delivering_is_not_cancelled_by_one_good_week(monkeypatch):
    """Cumpriu a última (100%), mas vinha fechando 50-60% do prescrito: a mediana pesa."""

    data = _with_ledger(monkeypatch, [
        _week(0, 30, 15), _week(1, 30, 16), _week(2, 30, 18), _week(3, 30, 15), _week(4, 30, 30),
    ])

    assert AthleteDossier._is_delivering(data) is False


def test_without_a_closed_week_with_prescription_it_is_not_delivering(monkeypatch):

    data = _with_ledger(monkeypatch, [_week(0, 0, 10), _week(1, 25, 0, in_progress=True)])

    assert AthleteDossier._is_delivering(data) is False


def test_the_answer_is_computed_once_per_dossier(monkeypatch):

    calls = []

    def ledger(data):

        calls.append(1)

        return data.weeks

    monkeypatch.setattr(AthleteDossier, "_ledger", staticmethod(ledger))

    data = _data([_week(0, 25, 26), _week(1, 25, 25), _week(2, 30, 30)])

    assert AthleteDossier._is_delivering(data) is True
    assert AthleteDossier._is_delivering(data) is True
    assert len(calls) == 1


def test_the_numbers_of_what_he_absorbed_feed_the_hold_text(monkeypatch):

    data = _with_ledger(monkeypatch, [_week(0, 25, 26), _week(1, 30, 30.5, 15.5)])

    text = AthleteDossier._held_numbers(data)

    assert "30 km" in text and "maior treino 16 km" in text and "prescrito 30 km" in text
