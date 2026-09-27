"""Quando chega o plano da semana que vem — fato no contexto do chat (o coach
disse "amanhã cedinho" num domingo às 19h; o plano sai às 20h)."""

from datetime import date, datetime
from unittest.mock import patch

from app.application.coach.conversation.conversation_context_builder import (
    ConversationContextBuilder,
)
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

SUNDAY = date(2026, 9, 27)


def _plan(week_start):

    return TrainingPlan(
        athlete_name="Renato", objective="x", phase="BUILD", weekly_volume=0,
        running_days=[], week_start=week_start, sessions=[],
    )


def _line(today, hour, week_start, external=False):

    with patch(
        "app.core.clock.now_local", return_value=datetime(2026, 9, 27, hour, 19),
    ):

        return ConversationContextBuilder._next_plan_line(
            make_runner(external_coach=external), _plan(week_start), today,
        )


def test_sunday_before_delivery_says_tonight_and_not_built_yet():

    line = _line(SUNDAY, 19, date(2026, 9, 21))

    assert "HOJE às 20h" in line and "AINDA NÃO FOI MONTADO" in line
    assert "28/09" in line


def test_after_delivery_says_it_is_already_there():

    assert "já montado e enviado" in _line(SUNDAY, 21, date(2026, 9, 28))


def test_midweek_points_to_sunday():

    line = _line(date(2026, 9, 23), 10, date(2026, 9, 21))

    assert "domingo (27/09) às 20h" in line


def test_external_coach_has_no_line():

    assert _line(SUNDAY, 19, date(2026, 9, 21), external=True) == ""
