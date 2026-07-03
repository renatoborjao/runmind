from datetime import date
from unittest.mock import MagicMock, patch

from app.application.planner.weekly_plan_service import WeeklyPlanService
from app.domain.entities.training_plan import TrainingPlan

MODULE = "app.application.planner.weekly_plan_service"

REFERENCE_DATE = date(2026, 7, 22)  # quarta-feira
CURRENT_WEEK_START = date(2026, 7, 20)  # segunda-feira desta semana
PREVIOUS_WEEK_START = date(2026, 7, 13)  # segunda-feira da semana passada


def _plan(week_start: date) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato",
        objective="10k",
        phase="BUILD",
        weekly_volume=30.0,
        running_days=["Monday", "Wednesday", "Sunday"],
        week_start=week_start,
        sessions=[],
    )


def test_reuses_existing_plan_when_same_iso_week():

    with (
        patch(f"{MODULE}.WeeklyPlanRepository") as mock_repo_cls,
        patch(f"{MODULE}.TrainingPlanner") as mock_planner,
    ):

        existing = _plan(CURRENT_WEEK_START)

        mock_repo = MagicMock()
        mock_repo.load.return_value = existing
        mock_repo_cls.return_value = mock_repo

        result = WeeklyPlanService.get_or_generate(
            profile="renato",
            runner=object(),
            assessment=object(),
            metrics=object(),
            goal=object(),
            reference_date=REFERENCE_DATE,
        )

        assert result is existing

        mock_planner.generate.assert_not_called()
        mock_repo.save.assert_not_called()


def test_regenerates_when_stored_plan_is_from_a_previous_week():

    with (
        patch(f"{MODULE}.WeeklyPlanRepository") as mock_repo_cls,
        patch(f"{MODULE}.TrainingPlanner") as mock_planner,
    ):

        stale = _plan(PREVIOUS_WEEK_START)

        fresh = _plan(CURRENT_WEEK_START)

        mock_repo = MagicMock()
        mock_repo.load.return_value = stale
        mock_repo_cls.return_value = mock_repo

        mock_planner.generate.return_value = fresh

        result = WeeklyPlanService.get_or_generate(
            profile="renato",
            runner=object(),
            assessment=object(),
            metrics=object(),
            goal=object(),
            reference_date=REFERENCE_DATE,
        )

        assert result is fresh

        mock_planner.generate.assert_called_once()

        _, kwargs = mock_planner.generate.call_args

        # week_start é passado posicionalmente — confere via call_args.args
        assert mock_planner.generate.call_args.args[-1] == CURRENT_WEEK_START

        mock_repo.save.assert_called_once_with("renato", fresh)


def test_generates_when_no_plan_exists_yet():

    with (
        patch(f"{MODULE}.WeeklyPlanRepository") as mock_repo_cls,
        patch(f"{MODULE}.TrainingPlanner") as mock_planner,
    ):

        fresh = _plan(CURRENT_WEEK_START)

        mock_repo = MagicMock()
        mock_repo.load.return_value = None
        mock_repo_cls.return_value = mock_repo

        mock_planner.generate.return_value = fresh

        result = WeeklyPlanService.get_or_generate(
            profile="renato",
            runner=object(),
            assessment=object(),
            metrics=object(),
            goal=object(),
            reference_date=REFERENCE_DATE,
        )

        assert result is fresh

        mock_repo.save.assert_called_once_with("renato", fresh)
