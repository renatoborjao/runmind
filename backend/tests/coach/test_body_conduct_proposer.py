import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.planning.body_conduct_engine import (
    BodyConductDecision,
)
from app.application.coach.planning.body_conduct_proposer import (
    BodyConductProposer,
)
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_STRAINED,
    BodyReading,
    RecoveryTrend,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_load import TrainingLoad
from app.domain.entities.training_plan import TrainingPlan

MOD = "app.application.coach.planning.body_conduct_proposer"

WEEK = date(2026, 7, 6)      # segunda
FRIDAY = date(2026, 7, 10)   # véspera do longão de sábado


def _reading(state=BODY_STRAINED) -> BodyReading:

    return BodyReading(
        load=TrainingLoad(
            acute_load=500.0, chronic_load=380.0, acwr=1.35,
            status="CAUTION", days_of_history=28,
        ),
        recovery=RecoveryTrend(days_covered=14),
        body_state=state,
        limiter="sono",
    )


def _plan() -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato", objective="10k", phase="IA",
        weekly_volume=30.0, running_days=["Tuesday", "Saturday"],
        week_start=WEEK,
        sessions=[
            PlannedSession("Tuesday", "Velocidade", "", 9.0, None, None, None),
            PlannedSession("Saturday", "Longão", "", 14.0, None, None, None),
        ],
    )


def _runner(external=False):

    return SimpleNamespace(name="Renato", external_coach=external)


_UNSET = object()


def _run(reading=None, plan=None, today=FRIDAY, runner=None, decision=_UNSET):

    reading = reading or _reading()
    plan = plan or _plan()
    runner = runner or _runner()

    ease = (
        BodyConductDecision(
            action="ease",
            operations=[
                {"action": "replace", "day": "Saturday", "session": {}}
            ],
            message="Vi teu corpo pedindo freio. Alivio o longão de amanhã?",
        )
        if decision is _UNSET
        else decision
    )

    repo = MagicMock()

    with patch(f"{MOD}.WeeklyPlanMatcher") as matcher, patch(
        f"{MOD}.BuildTrainingGoal"
    ) as goal, patch(
        f"{MOD}.BodyConductEngine.decide", new=AsyncMock(return_value=ease)
    ) as decide, patch(
        f"{MOD}.PlanProposalRepository", return_value=repo
    ):

        matcher.fulfilled_days.return_value = set()
        goal.execute.return_value = SimpleNamespace(name="10k")

        history = MagicMock(activities=[])

        message = asyncio.run(
            BodyConductProposer.propose(
                "renato", runner, plan, reading, None, history, today,
            )
        )

        return message, repo, decide


def test_eve_of_demanding_session_proposes_and_stages():

    message, repo, decide = _run()

    assert message is not None and "longão" in message
    # a proposta foi guardada pro 'sim' resolver depois
    repo.save.assert_called_once()
    saved = repo.save.call_args.args[1]
    assert saved.kind == "body_ease"


def test_healthy_body_never_proposes():

    message, repo, decide = _run(reading=_reading(BODY_ABSORBING))

    assert message is None
    decide.assert_not_awaited()
    repo.save.assert_not_called()


def test_too_early_does_not_propose():

    # quarta (08/07): o longão é sábado, não é véspera -> não antecipa o corte
    message, repo, decide = _run(today=date(2026, 7, 8))

    assert message is None
    decide.assert_not_awaited()


def test_external_coach_is_left_alone():

    message, repo, decide = _run(runner=_runner(external=True))

    assert message is None
    decide.assert_not_awaited()


def test_keep_decision_stages_nothing():

    keep = BodyConductDecision(action="keep", operations=[], message="")

    message, repo, decide = _run(decision=keep)

    assert message is None
    repo.save.assert_not_called()


def test_ai_failure_stages_nothing():

    # IA caiu (decide -> None): nada é proposto nem guardado
    message, repo, decide = _run(decision=None)

    assert message is None
    repo.save.assert_not_called()
