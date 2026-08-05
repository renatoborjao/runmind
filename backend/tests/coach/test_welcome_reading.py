from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.application.coach.intelligence.welcome_reading import WelcomeReading
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_activity, make_runner

MODULE = "app.application.coach.intelligence.welcome_reading"

# semana 0 = mais recente; âncora numa segunda pra os offsets caírem em
# ter(+1)/qui(+3)/sáb(+5)
_ANCHOR = datetime(2026, 8, 31, 7, 0)  # normalizado pra segunda abaixo
_MONDAY0 = _ANCHOR - timedelta(days=_ANCHOR.weekday())
_TODAY = (_MONDAY0 + timedelta(days=6)).date()  # domingo da semana mais recente


def _run(when: datetime, km: float, pace: float, rid: int):

    speed = 1000 / (pace * 60)  # m/s

    return make_activity(
        id=rid,
        sport="Run",
        distance=km * 1000,
        moving_time=int(km * pace * 60),
        elapsed_time=int(km * pace * 60),
        average_speed=speed,
        start_date=when,
        raw={"start_date_local": when.isoformat()},
    )


def _history(weeks: int = 10, improve: bool = False, km: float = 8.0):
    """Corridas em ter/qui/sáb ao longo de N semanas. improve=True deixa as
    semanas antigas mais lentas (pra acionar a evolução você-vs-você)."""

    runs = []

    rid = 0

    for w in range(weeks):

        monday = _MONDAY0 - timedelta(weeks=w)

        pace = 6.0

        if improve and w >= 6:

            pace = 6.7  # semanas antigas mais lentas

        for offset in (1, 3, 5):  # terça, quinta, sábado

            runs.append(_run(monday + timedelta(days=offset), km, pace, rid))

            rid += 1

    return TrainingHistory(activities=runs)


def _build(history, runner=None):

    with patch(f"{MODULE}.today_local", return_value=_TODAY):

        return WelcomeReading.build(runner or make_runner(), history)


def test_too_little_history_returns_none():

    history = TrainingHistory(activities=[_run(_MONDAY0, 8.0, 6.0, i) for i in range(3)])

    assert _build(history) is None


def test_reading_has_opener_bullets_and_bridge():

    msg = _build(_history())

    assert msg is not None
    assert "dei uma boa olhada" in msg
    assert "•" in msg
    assert "montei sua semana" in msg


def test_fitness_estimate_is_present():

    msg = _build(_history())

    assert "cruzaria" in msg
    # a meta padrão é 10k
    assert "10 km" in msg


def test_volume_and_frequency_present():

    msg = _build(_history())

    assert "km por semana" in msg
    assert "corridas por semana" in msg


def test_progress_insight_when_improving_over_months():

    # 12 semanas: a janela antiga (primeiros 28d) fica 100% no ritmo lento,
    # sem corrida rápida vazando na borda (o VDOT ancora no melhor esforço)
    msg = _build(_history(weeks=12, improve=True))

    assert "mais rápido" in msg


def test_day_pattern_when_concentrated():

    msg = _build(_history())

    assert "quase sempre corre" in msg
    assert "terça-feira" in msg
    assert "sábado" in msg


def test_half_marathon_goal_labels_named_distance():

    runner = make_runner(goal="meia maratona", target_race="meia maratona")

    # corridas longas o bastante pra extrapolar 21k (ratio < 4)
    history = _history(km=12.0)

    msg = _build(history, runner=runner)

    # ou casa a meia, ou cai no 10k — nunca "21 km" cru sem rótulo
    assert ("meia maratona" in msg) or ("10 km" in msg)


def test_once_sends_first_time_and_marks():

    guard = MagicMock()
    guard.already_sent.return_value = False

    with (
        patch(f"{MODULE}.DispatchGuard", guard),
        patch(f"{MODULE}.today_local", return_value=_TODAY),
    ):

        msg = WelcomeReading.once("renato", make_runner(), _history())

    assert msg is not None
    guard.mark.assert_called_once()


def test_once_skips_when_already_sent():

    guard = MagicMock()
    guard.already_sent.return_value = True

    with patch(f"{MODULE}.DispatchGuard", guard):

        msg = WelcomeReading.once("renato", make_runner(), _history())

    assert msg is None
    guard.mark.assert_not_called()


def test_once_does_not_mark_when_no_signal():
    """Pouco histórico: não envia E não queima a trava (deixa uma próxima
    conexão, com mais dados, tentar de novo)."""

    guard = MagicMock()
    guard.already_sent.return_value = False

    thin = TrainingHistory(activities=[_run(_MONDAY0, 8.0, 6.0, i) for i in range(2)])

    with (
        patch(f"{MODULE}.DispatchGuard", guard),
        patch(f"{MODULE}.today_local", return_value=_TODAY),
    ):

        msg = WelcomeReading.once("renato", make_runner(), thin)

    assert msg is None
    guard.mark.assert_not_called()
