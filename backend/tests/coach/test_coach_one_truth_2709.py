"""Varredura final 27/09 — o que o banco de cenários achou no código NO AR:

- texto do coach saindo SEM acento (Maurício/Leonardo/João);
- "não consegui agendar no Garmin" quando só não sobrou treino pra agendar, e o
  coach prometendo "vou tentar sincronizar" sem ter como (Renato);
- treino de HOJE já feito aparecendo "a fazer" (Fernanda);
- a mesma lacuna de estímulo listada duas vezes (João);
- atleta doente lido como "descansado, com folga pra puxar" (Hélio)."""

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.conversation.coach_brain import (
    PROMPT_TEMPLATE,
    BrainAction,
    CoachBrain,
)
from app.application.coach.conversation.coach_brain_executor import (
    CoachBrainExecutor,
)
from app.application.garmin.garmin_sync import GarminSync
from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.integrations.gemini import client as gemini_client
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    generate_text,
    unaccented_portuguese,
)
from tests.coach.factories import make_runner

GEMINI = "app.infrastructure.integrations.gemini.client"

SEM_ACENTO = (
    "Mauricio, amanha e dia de tiros, mas voce nao dormiu bem e a recuperacao "
    "caiu. Minha recomendacao e encurtar."
)

COM_ACENTO = (
    "Maurício, amanhã é dia de tiros, mas você não dormiu bem e a recuperação "
    "caiu. Minha recomendação é encurtar."
)


# ---- acento --------------------------------------------------------------


def test_detects_portuguese_written_without_accents():

    assert unaccented_portuguese(SEM_ACENTO)
    assert not unaccented_portuguese(COM_ACENTO)
    assert not unaccented_portuguese('{"action": "keep", "message": ""}')
    assert not unaccented_portuguese("ok, nao")  # 1 palavra só não dispara


def _responses(*texts):

    return AsyncMock(side_effect=[SimpleNamespace(text=t) for t in texts])


def _client(generate):

    mock = MagicMock()

    mock.aio.models.generate_content = generate

    return mock


def test_prose_without_accents_is_regenerated():

    generate = _responses(SEM_ACENTO, COM_ACENTO)

    with patch(f"{GEMINI}._client", return_value=_client(generate)):

        text = asyncio.run(
            generate_text(
                "m", "p", SimpleNamespace(thinking_config=None), portuguese=True,
            )
        )

    assert text == COM_ACENTO
    assert generate.await_count == 2


def test_json_without_accents_is_regenerated_and_best_is_kept():

    bad = '{"message": "%s"}' % SEM_ACENTO
    good = '{"message": "%s"}' % COM_ACENTO

    generate = _responses(bad, good)

    with patch(f"{GEMINI}._client", return_value=_client(generate)):

        result = asyncio.run(
            generate_json(
                "m", "p", SimpleNamespace(thinking_config=None),
                parse=lambda raw: raw,
            )
        )

    assert result == good


def test_json_always_unaccented_still_delivers_something():

    bad = '{"message": "%s"}' % SEM_ACENTO

    generate = _responses(bad, bad, bad)

    with patch(f"{GEMINI}._client", return_value=_client(generate)):

        result = asyncio.run(
            generate_json(
                "m", "p", SimpleNamespace(thinking_config=None),
                parse=lambda raw: raw,
            )
        )

    assert result == bad  # sem acento > nada


# ---- relógio -------------------------------------------------------------


def _push(results):

    with (
        patch(
            "app.application.garmin.garmin_sync.GarminClient.is_connected",
            return_value=True,
        ),
        patch(
            "app.application.garmin.garmin_sync.push_current_plan",
            new=AsyncMock(return_value=(None, None, results)),
        ),
        patch("app.application.garmin.garmin_sync.GarminOfferStore"),
    ):

        return asyncio.run(GarminSync._push("renato2", make_runner()))


def test_nothing_left_to_schedule_is_not_a_failure():

    reply = _push([])

    assert "Relógio em dia" in reply and "Não consegui" not in reply


def test_real_failure_still_says_so():

    reply = _push([{"ok": False, "action": "failed", "day": "Tuesday"}])

    assert "Não consegui" in reply


def test_brain_sends_to_the_watch_instead_of_promising():

    decision = CoachBrain._parse(
        '{"say": "", "actions": [{"type": "watch"}]}'
    )

    assert decision.actions[0].type == "watch"
    assert "MANDAR PRO RELÓGIO" in PROMPT_TEMPLATE

    action = BrainAction(
        type="watch", scope="week", target_day=None, instruction="",
    )

    with patch.object(
        GarminSync, "_push", new=AsyncMock(return_value="⌚ Mandei"),
    ) as push:

        reply = asyncio.run(
            CoachBrainExecutor._act_all(
                "renato2", make_runner(), [action], MagicMock(), "sim",
            )
        )

    push.assert_awaited_once()
    assert reply == "⌚ Mandei"


def test_watch_goes_last_after_the_week_changed():

    order = []

    async def skip(profile, runner, action):

        order.append("skip")

        return "🗓️ tirei", True

    async def watch(profile, runner):

        order.append("watch")

        return "⌚ relógio"

    actions = [
        BrainAction(type="watch", scope="week", target_day=None, instruction=""),
        BrainAction(
            type="skip", scope="single_session", target_day="Sunday",
            instruction="",
        ),
    ]

    with (
        patch.object(CoachBrainExecutor, "_skip", side_effect=skip),
        patch.object(CoachBrainExecutor, "_watch", side_effect=watch),
    ):

        asyncio.run(
            CoachBrainExecutor._act_all(
                "renato2", make_runner(), actions, MagicMock(), "msg",
            )
        )

    assert order == ["skip", "watch"]


# ---- plano: treino de HOJE já feito --------------------------------------


def _plan():

    sessions = [
        PlannedSession("Friday", "Tempo Run", "", 5.5, None, None, None),
        PlannedSession("Sunday", "Longão Progressivo", "", 8.5, None, None, None),
    ]

    return TrainingPlan(
        athlete_name="Fernanda", objective="10k", phase="BUILD",
        weekly_volume=14.0, running_days=["Friday", "Sunday"],
        week_start=date(2026, 9, 21), sessions=sessions,
    )


def test_today_session_already_done_is_marked_done():

    lines = WeeklyPlanMessageFormatter.session_lines(
        _plan(), date(2026, 9, 27), done_days={"Friday", "Sunday"},
    )

    sunday = next(l for l in lines if "domingo" in l)

    assert "✅ (feito)" in sunday


def test_today_session_not_done_yet_keeps_the_details():

    lines = WeeklyPlanMessageFormatter.session_lines(
        _plan(), date(2026, 9, 27), done_days={"Friday"},
    )

    sunday = next(l for l in lines if "domingo" in l)

    assert "✅" not in sunday and "❌" not in sunday


# ---- lacunas sem duplicata -----------------------------------------------


def test_a_gap_is_listed_once():

    from app.application.history.stimulus_ledger import StimulusLedger
    from app.domain.entities.training_goal import TrainingGoal

    text = StimulusLedger._gaps(
        {},
        TrainingGoal(
            name="5 km em 23 min", distance_km=5, target_time="00:23:00",
            race_date=None,
        ),
        date(2026, 9, 27),
    )

    gaps = text.split("LACUNAS: ")[1].rstrip(".").split("; ")
    families = [g.split(" (")[0] for g in gaps]

    assert len(families) == len(set(families))


# ---- doença em aberto no corpo -------------------------------------------


def test_open_illness_overrides_the_fresh_body_reading():

    from app.application.coach.context.athlete_dossier import AthleteDossier
    from app.domain.entities.daily_checkin import DailyCheckin

    ill = DailyCheckin(
        day="2026-09-22", at="2026-09-22T08:00:00", illness=True,
        note="Estou resfriado",
    )

    data = SimpleNamespace(
        reading=None, profile="helio", activities=[], today=date(2026, 9, 27),
        trajectory=None, drift=None, ceiling=None,
    )

    with (
        patch.object(AthleteDossier, "_open_illness", return_value=ill),
        patch(
            "app.application.coach.planning.body_directive.body_plan_directive",
            return_value="",
        ),
    ):

        lines = AthleteDossier._body(data)

    text = "\n".join(l for l in lines if l)

    assert "DOENÇA EM ABERTO" in text and "22/09" in text
    assert "não é folga pra puxar" in text
