import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch

from app.application.coach.planning.plan_realism_reviewer import (
    PlanRealismReviewer,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_runner

MODULE = "app.application.coach.planning.plan_realism_reviewer"


def _plan(reviewed: bool = False, source: str = "runmind") -> TrainingPlan:

    session = PlannedSession(
        day="Monday",
        workout_type="EASY",
        objective="Base",
        planned_distance_km=1.2,
        planned_duration_minutes=None,
        target_pace_min="7:45",
        target_pace_max="8:21",
    )

    return TrainingPlan(
        athlete_name="Adolfo",
        objective="Saúde",
        phase="BASE",
        weekly_volume=0.0,
        running_days=["Monday"],
        week_start=date(2026, 7, 6),
        sessions=[session],
        source=source,
        reviewed=reviewed,
    )


def _run(plan, response=None, error=None):

    generate = AsyncMock(
        return_value=response or "",
        side_effect=error,
    )

    with (
        patch(f"{MODULE}.generate_text", new=generate),
        patch(f"{MODULE}.WeeklyPlanRepository") as repo,
    ):

        result = asyncio.run(
            PlanRealismReviewer.ensure_reviewed(
                "adolfo",
                make_runner(
                    weight=138.0, height=1.88,
                    mobility="run_walker", continuous_run_minutes=1.0,
                ),
                plan,
            )
        )

        return result, generate, repo


def test_flags_unrealistic_session_with_a_note():

    result, _, repo = _run(
        _plan(),
        response=(
            '{"concerns": [{"day": "Monday", "note": "Correr 1,2 km sem '
            'parar é demais agora — faça trote curto e caminhada."}]}'
        ),
    )

    session = result.sessions[0]

    assert session.adjusted is True
    assert "trote" in session.adjustment_reason.lower()

    # revisado e persistido
    assert result.reviewed is True
    repo.return_value.save.assert_called_once()


def test_ai_failure_keeps_plan_intact():

    result, _, repo = _run(_plan(), error=RuntimeError("gemini fora do ar"))

    assert result.sessions[0].adjusted is False
    # reviewed continua False pra tentar de novo na próxima entrega
    assert result.reviewed is False
    repo.return_value.save.assert_not_called()


def test_empty_concerns_marks_reviewed_without_adjusting():

    result, _, repo = _run(_plan(), response='{"concerns": []}')

    assert result.sessions[0].adjusted is False
    assert result.reviewed is True
    repo.return_value.save.assert_called_once()


def test_skips_when_already_reviewed():

    _, generate, repo = _run(_plan(reviewed=True), response='{"concerns": []}')

    generate.assert_not_awaited()
    repo.return_value.save.assert_not_called()


def test_skips_external_coach_plan():

    _, generate, _ = _run(
        _plan(source="externo"),
        response='{"concerns": []}',
    )

    generate.assert_not_awaited()


# ==========================================================
# Capar números (só reduz, com piso)
# ==========================================================

def _long_plan(km: float = 9.1) -> TrainingPlan:

    session = PlannedSession(
        day="Saturday",
        workout_type="LONG_RUN",
        objective="Resistência",
        planned_distance_km=km,
        planned_duration_minutes=None,
        target_pace_min=None,
        target_pace_max=None,
    )

    return TrainingPlan(
        athlete_name="X",
        objective="Saúde",
        phase="BASE",
        weekly_volume=0.0,
        running_days=["Saturday"],
        week_start=date(2026, 7, 6),
        sessions=[session],
    )


def _review(plan, response):

    with (
        patch(f"{MODULE}.generate_text", new=AsyncMock(return_value=response)),
        patch(f"{MODULE}.WeeklyPlanRepository"),
    ):

        return asyncio.run(
            PlanRealismReviewer.ensure_reviewed("x", make_runner(), plan)
        )


def test_caps_distance_down_to_suggested():

    result = _review(
        _long_plan(9.1),
        '{"concerns": [{"day": "Saturday", "note": "muito longo",'
        ' "suggested_max_km": 5.0}]}',
    )

    session = result.sessions[0]
    assert session.planned_distance_km == 5.0
    assert session.adjusted is True


def test_cap_never_increases_distance():

    result = _review(
        _long_plan(5.0),
        '{"concerns": [{"day": "Saturday", "note": "x",'
        ' "suggested_max_km": 8.0}]}',
    )

    # teto acima do planejado é ignorado — nunca aumenta
    assert result.sessions[0].planned_distance_km == 5.0


def test_cap_is_floored_to_avoid_absurd_shrink():

    result = _review(
        _long_plan(9.1),
        '{"concerns": [{"day": "Saturday", "note": "x",'
        ' "suggested_max_km": 0.5}]}',
    )

    # piso = max(1.0, 40% de 9.1) = 3.6 km
    assert result.sessions[0].planned_distance_km == 3.6


def test_note_without_cap_only_flags():

    result = _review(
        _long_plan(9.1),
        '{"concerns": [{"day": "Saturday", "note": "cuidado com o ritmo"}]}',
    )

    session = result.sessions[0]
    assert session.planned_distance_km == 9.1  # número intacto
    assert session.adjusted is True
