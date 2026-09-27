"""Atleta DOENTE: o coach tira a semana na hora e os proativos não cobram.

Caso real (Hélio, 22-27/09): "Estou resfriado e não vou conseguir cumprir o
plano semanal". O cérebro emitiu skip da SEMANA, mas o MoveSkipEngine só entende
UM dia — nada foi aplicado e o coach prometeu "vou pausar e pular os treinos".
No sábado o bom dia mandou o longão de 10,5 km; no domingo, a cobrança do furo
("o que tá pegando na rotina?")."""

import asyncio
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.conversation.coach_brain import (
    PROMPT_TEMPLATE,
    BrainAction,
)
from app.application.coach.conversation.coach_brain_executor import (
    CoachBrainExecutor,
)
from app.application.coach.intelligence.illness_episode import IllnessEpisode
from app.domain.entities.daily_checkin import DailyCheckin
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_activity, make_runner

EXECUTOR = "app.application.coach.conversation.coach_brain_executor"
EPISODE = "app.application.coach.intelligence.illness_episode"

WEEK = date(2026, 9, 21)  # segunda
TUESDAY = date(2026, 9, 22)


def _plan() -> TrainingPlan:

    sessions = [
        PlannedSession(day, wtype, "", km, None, None, None)
        for day, wtype, km in (
            ("Tuesday", "Fartlek", 6.0),
            ("Thursday", "Rodagem Leve", 6.0),
            ("Saturday", "Longão Progressivo", 10.5),
        )
    ]

    return TrainingPlan(
        athlete_name="Hélio", objective="10k", phase="BUILD",
        weekly_volume=22.5, running_days=[s.day for s in sessions],
        week_start=WEEK, sessions=sessions,
    )


def _skip(action, fulfilled=frozenset(), external=False, today=TUESDAY):

    applied = {}

    def apply(profile, proposal):

        applied["proposal"] = proposal

        return _plan()

    runner = make_runner(name="Hélio")
    runner.external_coach = external

    with (
        patch(
            f"{EXECUTOR}.CurrentPlanProvider.for_profile",
            new=AsyncMock(return_value=(runner, _plan())),
        ),
        patch(
            "app.application.use_cases.load_training_history."
            "LoadTrainingHistory.execute",
            new=AsyncMock(return_value=TrainingHistory([])),
        ),
        patch(
            "app.application.planner.weekly_plan_matcher.WeeklyPlanMatcher."
            "fulfilled_days",
            return_value=set(fulfilled),
        ),
        patch(f"{EXECUTOR}.today_local", return_value=today),
        patch(f"{EXECUTOR}.PlanChangeApplier.apply", side_effect=apply),
        patch(f"{EXECUTOR}.watch_update_offer", return_value=" [relógio]"),
    ):

        reply, removed = asyncio.run(
            CoachBrainExecutor._skip("helio", runner, action)
        )

    proposal = applied.get("proposal")

    assert removed == (proposal is not None)

    return reply, [op["day"] for op in proposal.operations] if proposal else None


WEEK_SKIP = BrainAction(
    type="skip", scope="week", target_day=None, instruction="pular a semana",
)


def _day_skip(day):

    return BrainAction(
        type="skip", scope="single_session", target_day=day,
        instruction="não vou conseguir",
    )


# ---- executor: pular a SEMANA -------------------------------------------


def test_skip_week_drops_every_remaining_session_now():

    reply, dropped = _skip(WEEK_SKIP)

    assert dropped == ["Tuesday", "Thursday", "Saturday"]
    assert "Tirei os treinos que faltavam" in reply and "[relógio]" in reply


def test_skip_week_keeps_what_was_already_done():

    reply, dropped = _skip(WEEK_SKIP, fulfilled={"Tuesday"})

    assert dropped == ["Thursday", "Saturday"]


def test_skip_week_with_nothing_left_says_so():

    reply, dropped = _skip(WEEK_SKIP, today=date(2026, 9, 27))  # domingo

    assert dropped is None
    assert "não sobrou treino" in reply


def test_skip_never_touches_an_external_coach_plan():

    reply, dropped = _skip(WEEK_SKIP, external=True)

    assert reply is None and dropped is None


# ---- executor: pular UM dia ---------------------------------------------


def test_skip_today_drops_it_and_says_exactly_what_left():

    reply, dropped = _skip(_day_skip("Tuesday"))

    assert dropped == ["Tuesday"]
    assert "Tirei o treino de terça-feira" in reply


def test_skip_a_day_without_training_never_claims_it_removed_something():
    """Lab 27/09: "hoje não vou conseguir, tô gripado" num domingo SEM treino —
    o coach dizia "já tirei o treino de hoje". Agora diz que não havia."""

    reply, dropped = _skip(_day_skip("Sunday"), today=date(2026, 9, 27))

    assert dropped is None
    assert "não tinha treino" in reply and "Tirei" not in reply


def test_skip_a_session_already_done_is_not_removed():

    reply, dropped = _skip(_day_skip("Tuesday"), fulfilled={"Tuesday"})

    assert dropped is None
    assert "já fez" in reply


def test_skip_is_applied_not_proposed():
    """Pular vai pro _skip (aplica); nunca vira proposta esperando um 'sim' que
    o atleta doente não manda."""

    with (
        patch.object(
            CoachBrainExecutor, "_skip",
            new=AsyncMock(return_value=("🗓️ Tirei os treinos", True)),
        ) as skip,
        patch.object(CoachBrainExecutor, "_propose", new=AsyncMock()) as propose,
    ):

        reply = asyncio.run(
            CoachBrainExecutor._act_all(
                "helio", make_runner(), [WEEK_SKIP], MagicMock(), "msg", "",
                "Melhoras, Hélio!",
            )
        )

    skip.assert_awaited_once()
    propose.assert_not_awaited()
    assert reply.startswith("Melhoras, Hélio!") and "Tirei os treinos" in reply


def test_two_skips_and_a_move_all_happen():
    """"pula terça e quinta e passa o longão pra domingo": os pulos saem na
    hora, a troca vira proposta — nada fica de fora."""

    actions = [
        _day_skip("Tuesday"), _day_skip("Thursday"),
        BrainAction(
            type="move", scope="single_session", target_day="Sunday",
            instruction="longão pro domingo",
        ),
    ]

    skip = AsyncMock(
        side_effect=[("🗓️ terça fora", True), ("🗓️ quinta fora", True)],
    )

    with (
        patch.object(CoachBrainExecutor, "_skip", new=skip),
        patch.object(
            CoachBrainExecutor, "_propose", new=AsyncMock(return_value="posso?"),
        ),
        patch.object(
            CoachBrainExecutor, "_oneoff_correction",
            new=AsyncMock(return_value=None),
        ),
    ):

        reply = asyncio.run(
            CoachBrainExecutor._act_all(
                "helio", make_runner(), actions, MagicMock(), "msg",
            )
        )

    assert skip.await_count == 2
    assert "terça fora" in reply and "quinta fora" in reply and "posso?" in reply


def test_skip_without_a_resolved_day_keeps_the_proposal_path():

    action = BrainAction(
        type="skip", scope="single_session", target_day=None,
        instruction="pular um treino",
    )

    assert not CoachBrainExecutor._skips(action)


def test_brain_knows_skip_is_applied_by_the_system():

    assert "PULAR NÃO É PROPOSTA" in PROMPT_TEMPLATE
    assert "(mover de dia, pular," not in PROMPT_TEMPLATE


# ---- episódio de doença --------------------------------------------------


def _open(checkin, activities):

    repo = MagicMock()
    repo.recent_illness.return_value = checkin

    with patch(f"{EPISODE}.CheckinRepository", return_value=repo):

        return IllnessEpisode.open("helio", activities, date(2026, 9, 27))


def _ill(day="2026-09-22"):

    return DailyCheckin(
        day=day, at=f"{day}T08:32:41", illness=True, note="Estou resfriado",
    )


def test_illness_is_open_while_he_has_not_run_since():

    earlier = make_activity(start_date=datetime(2026, 9, 21, 7, 0))

    assert _open(_ill(), [earlier]) is not None


def test_running_again_closes_the_episode():

    back = make_activity(start_date=datetime(2026, 9, 25, 7, 0))

    assert _open(_ill(), [back]) is None


def test_no_recent_illness_no_episode():

    assert _open(None, []) is None


def test_reminder_line_orients_without_charging():

    line = IllnessEpisode.reminder_line(_ill())

    assert "22/09" in line and "pula sem culpa" in line


def test_nothing_removed_drops_the_coach_claim():
    """O cérebro disse "cancelei o treino de hoje" num domingo SEM treino: fica
    só a verdade do sistema, nunca as duas frases se contradizendo."""

    action = BrainAction(
        type="skip", scope="single_session", target_day="Sunday",
        instruction="cancelar hoje",
    )

    with patch.object(
        CoachBrainExecutor, "_skip",
        new=AsyncMock(return_value=("🗓️ Domingo não tinha treino", False)),
    ):

        reply = asyncio.run(
            CoachBrainExecutor._act_all(
                "helio", make_runner(), [action], MagicMock(), "msg", "",
                "Cancelei o treino de hoje!",
            )
        )

    assert reply == "🗓️ Domingo não tinha treino"
