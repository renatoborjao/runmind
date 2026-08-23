import asyncio
from datetime import date, datetime, timedelta
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
    assert _touchpoint(5) == "race_week"
    assert _touchpoint(3) == "journey"
    assert _touchpoint(2) == "journey"
    assert _touchpoint(1) == "eve"
    assert _touchpoint(0) == "race_day"


def test_touchpoint_skips_already_sent():
    """Cadastrou a prova em cima da hora (5 dias): o taper foi perdido, pega
    o marco atual (semana da prova)."""

    assert _touchpoint(5, sent=("taper",)) == "race_week"


def test_touchpoint_does_not_fall_through_to_farther_marker():
    """Bug do Renato (recebeu o 'polimento' a 4 dias da prova): com a 'semana
    da prova' JÁ enviada, o bracket de hoje (4-7 dias = race_week) não deve cair
    pro marco seguinte (taper, de ~2 semanas antes). Já saiu -> None, silêncio."""

    assert _touchpoint(4, sent=("race_week",)) is None
    assert _touchpoint(6, sent=("race_week",)) is None
    # e o taper NÃO re-dispara depois do seu bracket, mesmo que nada mais tenha saído
    assert _touchpoint(5, sent=("taper", "race_week")) is None


def test_touchpoint_none_when_past_or_far():

    assert _touchpoint(-1) is None
    assert _touchpoint(20) is None


def test_preview_lists_upcoming_touches_with_dates():
    """Dry-run: a 4 dias da prova, mostra a sequência que AINDA vai sair —
    semana-da-prova (hoje), jornada (3d), véspera (1d) e dia da prova — cada
    marco UMA vez, com data e conteúdo montado."""

    with (
        patch(f"{MODULE}.LoadRunnerProfile") as load,
        patch(f"{MODULE}.BuildTrainingGoal") as build_goal,
        patch(f"{MODULE}.use_athlete_timezone"),
        patch(f"{MODULE}.today_local", return_value=date(2026, 8, 19)),
        patch(f"{MODULE}.DispatchGuard") as guard,
        patch.object(
            RaceCompanionNotifier, "_message",
            new=AsyncMock(side_effect=lambda p, r, g, touch: f"MSG-{touch}"),
        ),
    ):

        load.execute.return_value = make_runner(name="Renato")
        build_goal.execute.return_value = _goal()   # prova 2026-08-23
        guard.already_sent.return_value = False

        schedule = asyncio.run(RaceCompanionNotifier.preview("renato2"))

    touches = [(row["date"], row["touch"]) for row in schedule]

    assert touches == [
        ("2026-08-19", "race_week"),
        ("2026-08-20", "journey"),
        ("2026-08-22", "eve"),
        ("2026-08-23", "race_day"),
    ]
    assert all(row["will_send"] for row in schedule)
    assert schedule[1]["preview"] == "MSG-journey"


def test_preview_marks_already_sent_without_building():

    with (
        patch(f"{MODULE}.LoadRunnerProfile") as load,
        patch(f"{MODULE}.BuildTrainingGoal") as build_goal,
        patch(f"{MODULE}.use_athlete_timezone"),
        patch(f"{MODULE}.today_local", return_value=date(2026, 8, 19)),
        patch(f"{MODULE}.DispatchGuard") as guard,
        patch.object(
            RaceCompanionNotifier, "_message",
            new=AsyncMock(side_effect=lambda p, r, g, touch: f"MSG-{touch}"),
        ),
    ):

        load.execute.return_value = make_runner(name="Renato")
        build_goal.execute.return_value = _goal()
        # semana-da-prova já saiu -> aparece marcada, sem montar conteúdo
        guard.already_sent.side_effect = (
            lambda k, p, period: period.endswith(":race_week")
        )

        schedule = asyncio.run(RaceCompanionNotifier.preview("renato2"))

    race_week = next(r for r in schedule if r["touch"] == "race_week")

    assert race_week["already_sent"] is True
    assert race_week["will_send"] is False
    assert race_week["preview"] == ""


# --- gate de hora no _notify_one: a manhã da prova sai CEDO ---


def _run_notify(hour, days_until=0, sent=()):
    """Roda _notify_one com relógio na `hour` local e a prova a `days_until`
    dias. Devolve o mock de CoachOutbox.send pra checar se (e o quê) saiu."""

    race = date(2026, 8, 23)
    today = race - timedelta(days=days_until)

    with (
        patch(f"{MODULE}.LoadRunnerProfile") as load,
        patch(f"{MODULE}.BuildTrainingGoal") as build_goal,
        patch(f"{MODULE}.use_athlete_timezone"),
        patch(
            f"{MODULE}.now_in",
            return_value=datetime(today.year, today.month, today.day, hour, 0),
        ),
        patch(f"{MODULE}.today_local", return_value=today),
        patch(f"{MODULE}.DispatchGuard") as guard,
        patch(f"{MODULE}.CoachOutbox") as outbox,
        patch.object(
            RaceCompanionNotifier, "_message",
            new=AsyncMock(side_effect=lambda p, r, g, touch: f"MSG-{touch}"),
        ),
    ):

        load.execute.return_value = make_runner(name="Renato")
        build_goal.execute.return_value = _goal(race)
        guard.already_sent.side_effect = (
            lambda k, p, period: period.split(":")[-1] in sent
        )
        outbox.send = AsyncMock()

        asyncio.run(RaceCompanionNotifier._notify_one("renato2"))

        return outbox.send


def _sent_touch(send_mock):
    if not send_mock.await_count:
        return None
    return send_mock.await_args.args[1]  # (runner, message, ...)


def test_race_day_fires_early_in_the_morning():
    """A manhã da prova sai CEDO — a partir das 5h, a primeira coisa do dia
    (a queixa do Renato: o 'É HOJE!' só saía às 7h)."""

    assert _sent_touch(_run_notify(hour=5)) == "MSG-race_day"
    assert _sent_touch(_run_notify(hour=6)) == "MSG-race_day"
    assert _sent_touch(_run_notify(hour=7)) == "MSG-race_day"


def test_race_day_silent_before_window_and_late():

    assert _run_notify(hour=4).await_count == 0
    assert _run_notify(hour=12).await_count == 0


def test_non_race_day_touch_still_gates_at_seven():
    """Véspera (e os demais) continuam saindo só às 7h — a janela cedo é só
    do dia da prova."""

    assert _run_notify(hour=5, days_until=1).await_count == 0
    assert _sent_touch(_run_notify(hour=7, days_until=1)) == "MSG-eve"


def test_race_day_not_resent_if_already_sent():
    """Já mandamos o 'É HOJE!' num tique anterior (ou manualmente): não repete."""

    assert _run_notify(hour=6, sent=("race_day",)).await_count == 0


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
