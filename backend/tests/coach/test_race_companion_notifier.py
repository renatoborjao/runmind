import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch

from app.application.review.race_companion_notifier import (
    RaceCompanionNotifier,
)
from app.domain.entities.training_goal import TrainingGoal
from tests.coach.factories import make_runner

MODULE = "app.application.review.race_companion_notifier"


def _goal(race_date=date(2026, 8, 23)):
    return TrainingGoal(
        name="10 km sub-50", distance_km=10.0,
        target_time="00:50:00", race_date=race_date,
    )


def _touchpoint(days_until, sent=()):
    """Roda _touchpoint com DispatchGuard mockado (sent = marcos já enviados)."""

    with patch(f"{MODULE}.DispatchGuard") as guard:

        guard.already_sent.side_effect = (
            lambda kind, profile, period: period.split(":")[-1] in sent
        )

        return RaceCompanionNotifier._touchpoint("p", days_until, _goal())


def test_touchpoint_picks_the_right_marker():

    assert _touchpoint(14) == "taper"
    assert _touchpoint(10) == "taper"
    assert _touchpoint(7) == "race_week"
    assert _touchpoint(3) == "race_week"
    assert _touchpoint(1) == "eve"
    assert _touchpoint(0) == "race_day"


def test_touchpoint_skips_already_sent():
    """Cadastrou a prova em cima da hora (3 dias): o taper foi perdido, pega
    o marco atual (semana da prova)."""

    assert _touchpoint(3, sent=("taper",)) == "race_week"


def test_touchpoint_none_when_past_or_far():

    assert _touchpoint(-1) is None
    assert _touchpoint(20) is None


def _message(touch, runner=None):
    runner = runner or make_runner(external_coach=False)
    with patch.object(
        RaceCompanionNotifier, "_pace_line", new=AsyncMock(return_value=None)
    ):
        return asyncio.run(
            RaceCompanionNotifier._message("p", runner, _goal(), touch)
        )


def test_message_taper_only_for_our_athletes():

    ours = _message("taper", make_runner(external_coach=False))
    external = _message("taper", make_runner(external_coach=True))

    assert ours is not None and "polimento" in ours.lower()
    # de treinador externo o polimento é do treinador dele -> não fala
    assert external is None


def test_message_uses_race_distance_not_goal_aspiration():
    """Bug real do Renato: a prova (10k) era rotulada com o OBJETIVO de fundo
    (goal.name = 'correr 21 km, buscar saúde...') → 'polimento pra 21km'. Tem
    que citar a PROVA (10 km), nunca a aspiração."""

    runner = make_runner(external_coach=False)

    goal = TrainingGoal(
        name="correr 21 km, buscar saúde/evolução e correr mais rápido",
        distance_km=10.0, target_time=None, race_date=date(2026, 8, 23),
    )

    with patch.object(
        RaceCompanionNotifier, "_pace_line", new=AsyncMock(return_value=None)
    ):
        msg = asyncio.run(
            RaceCompanionNotifier._message("p", runner, goal, "taper")
        )

    assert "10 km" in msg
    assert "21 km" not in msg
    assert "saúde" not in msg  # a aspiração não vaza como nome da prova


def test_message_race_day_is_energizing():

    msg = _message("race_day")

    assert "HOJE" in msg
    assert "Boa prova" in msg


def test_message_eve_has_checklist():

    msg = _message("eve")

    assert "Amanhã" in msg
    assert "nada novo" in msg.lower()


def test_pace_line_embedded_when_available():

    runner = make_runner(external_coach=False)

    with patch.object(
        RaceCompanionNotifier,
        "_pace_line",
        new=AsyncMock(return_value="🎯 Lembrete: pace-alvo ~5:00/km"),
    ):
        msg = asyncio.run(
            RaceCompanionNotifier._message("p", runner, _goal(), "race_week")
        )

    assert "5:00/km" in msg
