import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch

from app.application.coach.conversation.negotiation_flow import NegotiationFlow
from app.application.coach.planning.negotiation_engine import Negotiation
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

MODULE = "app.application.coach.conversation.negotiation_flow"


def _plan():
    return TrainingPlan(
        athlete_name="Renato", objective="10k", phase="BUILD",
        weekly_volume=28.0, running_days=["Tuesday"],
        week_start=date(2026, 7, 13),
        sessions=[
            PlannedSession(
                day="Tuesday", workout_type="VO2", objective="",
                planned_distance_km=8.0, planned_duration_minutes=None,
                target_pace_min="4:50", target_pace_max="5:00", kind="run",
            ),
        ],
    )


def test_gate_catches_load_adjustment_requests():

    yes = [
        "esse plano ta puxado demais, deixa mais leve",
        "quero mais rodagens essa semana",
        "da pra deixar a semana mais tranquila?",
        "acho que ta muito pesado o volume",
    ]
    no = [
        "como foi meu ultimo treino?",
        "bom dia coach",
        "minha prova e dia 20",
    ]

    for t in yes:
        assert NegotiationFlow._looks_like_negotiation(t) is True, t
    for t in no:
        assert NegotiationFlow._looks_like_negotiation(t) is False, t


def _run(text, runner=None, plan=None, negotiation="unset"):

    with (
        patch(f"{MODULE}.CurrentPlanProvider") as provider,
        patch(f"{MODULE}.NegotiationEngine") as engine,
        patch(f"{MODULE}.PlanProposalRepository") as repo_cls,
    ):

        provider.for_profile = AsyncMock(
            return_value=(runner or make_runner(), plan or _plan()),
        )

        if negotiation != "unset":
            engine.propose = AsyncMock(return_value=negotiation)

        reply = asyncio.run(
            NegotiationFlow.handle(
                "renato", runner or make_runner(), text,
            )
        )

        return reply, engine, repo_cls


def test_external_coach_never_negotiates():

    reply, engine, _ = _run(
        "deixa mais leve",
        runner=make_runner(external_coach=True),
    )

    assert reply is None
    engine.propose.assert_not_called()


def test_message_without_adjustment_cue_is_ignored():

    reply, engine, _ = _run("como foi meu treino?")

    assert reply is None
    engine.propose.assert_not_called()


def test_engine_declines_falls_through():

    reply, _, repo_cls = _run("deixa mais leve", negotiation=None)

    assert reply is None
    repo_cls.return_value.save.assert_not_called()


def test_accepted_negotiation_shows_revised_week_and_saves_proposal():

    negotiation = Negotiation(
        operations=[
            {"action": "replace", "day": "Tuesday", "session": {
                "day": "Tuesday", "workout_type": "Rodagem leve",
                "objective": "base", "planned_distance_km": 6.0,
                "planned_duration_minutes": None, "target_pace_min": "6:00",
                "target_pace_max": "6:30", "kind": "run",
                "structure": "6 km leves", "purpose": "base", "steps": [],
            }},
        ],
        message="Reduzi a carga mantendo o essencial rumo à meta.",
    )

    reply, _, repo_cls = _run("deixa mais leve", negotiation=negotiation)

    assert reply is not None
    assert "Reduzi a carga" in reply
    assert "Como fica sua semana" in reply
    assert "Rodagem leve" in reply          # a semana revisada aparece
    assert "sim" in reply.lower()            # pede confirmação
    repo_cls.return_value.save.assert_called_once()
    # a proposta guardada carrega as operações da negociação
    saved = repo_cls.return_value.save.call_args.args[1]
    assert saved.kind == "negotiation"
    assert saved.operations == negotiation.operations
