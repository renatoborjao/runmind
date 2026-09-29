from datetime import date, timedelta

from app.application.history.recovery_alert_run import RecoveryAlertRun
from app.domain.entities.daily_health import DailyHealth

START = date(2026, 7, 1)


def _series(days: int, hrv_of, rhr_of=lambda i: 55, wake_of=lambda i: 70):
    """`days` dias a partir de 01/07; hrv/rhr/bateria por índice do dia."""

    return [
        DailyHealth(
            date=(START + timedelta(days=i)).isoformat(),
            hrv_last_night=hrv_of(i),
            hrv_weekly_avg=hrv_of(i),
            resting_hr=rhr_of(i),
            body_battery_at_wake=wake_of(i),
            sleep_hours=7.5,
        )
        for i in range(days)
    ]


def _day(i: int) -> date:

    return START + timedelta(days=i)


def test_no_alert_when_recovery_is_in_his_band():

    series = _series(70, hrv_of=lambda i: 56)

    assert RecoveryAlertRun.since(series, _day(69)) is None


def test_alert_run_starts_when_the_recovery_actually_left_his_band():
    """60 dias com HRV ~56 e depois cai pra ~47: a sequência começa quando a
    MÉDIA de 7 dias sai da faixa, não quando houve a 1ª noite ruim."""

    series = _series(75, hrv_of=lambda i: 56 if i < 62 else 40)

    since = RecoveryAlertRun.since(series, _day(74))

    assert since is not None
    assert _day(62) <= since <= _day(70)
    # e vem CONTÍNUA até hoje
    assert since <= _day(74)


def test_one_great_night_does_not_hide_the_run_but_is_not_counted_as_the_alert():
    """A noite ótima de um dia (HRV 62, bateria 87) não desfaz uma tendência de
    7 dias — a sequência segue; o que o coach faz é RECONHECER a noite (prompt)."""

    def hrv(i):
        return 62 if i == 72 else (56 if i < 62 else 40)

    series = _series(75, hrv_of=hrv, wake_of=lambda i: 87 if i == 72 else 70)

    since = RecoveryAlertRun.since(series, _day(74))

    assert since is not None and since < _day(72)


def test_run_is_broken_by_a_recovered_stretch():

    # HRV cai, RECUPERA por >7 dias, e volta a cair: a sequência de hoje é só a última
    def hrv(i):
        if i < 40:
            return 56
        if i < 50:
            return 40
        if i < 65:
            return 60
        return 38

    series = _series(75, hrv_of=hrv)

    since = RecoveryAlertRun.since(series, _day(74))

    assert since is not None and since >= _day(65)


def test_low_waking_battery_alone_is_an_alert_day():

    series = _series(30, hrv_of=lambda i: 56, wake_of=lambda i: 20 if i >= 27 else 70)

    since = RecoveryAlertRun.since(series, _day(29))

    assert since == _day(27)


def test_empty_series_is_none():

    assert RecoveryAlertRun.since([], date(2026, 9, 29)) is None


def test_since_for_profile_never_raises():

    assert RecoveryAlertRun.since_for_profile("perfil-que-nao-existe-xyz", date(2026, 9, 29)) is None
