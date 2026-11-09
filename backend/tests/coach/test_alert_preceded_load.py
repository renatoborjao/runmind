"""A ORDEM no tempo: "carga alta + recuperação caindo" só é sobrecarga de treino se a carga veio
antes (ou junto). Renato 08/11: a recuperação caiu desde 29/10 (semana de 14,7 km, leve) e a
semana de 30 km veio DEPOIS — o cruzamento no tempo virou "sobrecarregado" e o plano foi cortado."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from app.application.coach.intelligence.body_reading_builder import BodyReadingBuilder
from app.domain.entities.training_load import LOAD_HIGH, LOAD_INSUFFICIENT, LOAD_OPTIMAL

MOD = "app.application.coach.intelligence.body_reading_builder"
TODAY = date(2026, 11, 8)


def _call(since, earlier_status, acwr=None):

    earlier = SimpleNamespace(status=earlier_status, acwr=acwr)

    with patch(
        "app.application.history.recovery_alert_run.RecoveryAlertRun.since", return_value=since
    ), patch(f"{MOD}.TrainingLoadAnalyzer.analyze", return_value=earlier):

        return BodyReadingBuilder._alert_preceded_load(
            series=[], activities=[], reference_date=TODAY,
            resting_hr=None, max_hr=None, sex=None, recent_race_date=None, zones=None,
        )


def test_alert_that_started_while_the_load_was_light_did_not_come_from_the_load():

    since, preceded = _call(date(2026, 10, 29), LOAD_OPTIMAL)

    assert since == date(2026, 10, 29) and preceded is True


def test_alert_that_started_with_the_load_already_high_stays_an_overload_signal():

    _, preceded = _call(date(2026, 10, 29), LOAD_HIGH)

    assert preceded is False


def test_a_fresh_alert_inside_the_acute_week_cannot_be_called_older_than_the_load():
    """Alerta de 3 dias: começou DENTRO da semana aguda — a carga pode ter causado."""

    _, preceded = _call(date(2026, 11, 5), LOAD_OPTIMAL)

    assert preceded is False


def test_without_a_known_alert_start_nothing_changes():

    since, preceded = _call(None, LOAD_OPTIMAL)

    assert since is None and preceded is False


def test_any_failure_leaves_the_verdict_as_it_was():

    with patch(
        "app.application.history.recovery_alert_run.RecoveryAlertRun.since",
        side_effect=RuntimeError("sem série"),
    ):

        assert BodyReadingBuilder._alert_preceded_load(
            series=[], activities=[], reference_date=TODAY,
            resting_hr=None, max_hr=None, sex=None, recent_race_date=None, zones=None,
        ) == (None, False)


def test_little_history_with_a_low_ratio_still_reads_as_light_load():
    """Renato em 29/10: só 20 dias de histórico (a parada zerou a janela), razão 0,59 — o status é
    "dados insuficientes", mas a razão baixa é leitura segura de carga leve."""

    _, preceded = _call(date(2026, 10, 29), LOAD_INSUFFICIENT, acwr=0.59)

    assert preceded is True


def test_little_history_with_no_ratio_or_a_high_one_proves_nothing():

    assert _call(date(2026, 10, 29), LOAD_INSUFFICIENT, acwr=None)[1] is False
    assert _call(date(2026, 10, 29), LOAD_INSUFFICIENT, acwr=1.6)[1] is False
