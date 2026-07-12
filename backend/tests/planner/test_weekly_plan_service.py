from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from app.application.planner.weekly_plan_service import WeeklyPlanService
from tests.coach.factories import make_runner
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


class _FakeHistoryRepo:

    def __init__(self, week_starts):

        self._plans = [_plan(ws) for ws in week_starts]

    def history(self, profile):

        return self._plans


def test_training_week_counts_prior_weeks():

    repo = _FakeHistoryRepo([
        date(2026, 7, 6),
        date(2026, 7, 13),
        date(2026, 7, 27),  # futura, não conta
    ])

    # current = 20/07: semanas anteriores {06, 13} -> 4ª semana... não,
    # 2 anteriores + 1 = 3ª semana de treino
    assert (
        WeeklyPlanService._training_week(repo, "renato", CURRENT_WEEK_START)
        == 3
    )


def test_training_week_is_one_without_history():

    repo = _FakeHistoryRepo([])

    assert (
        WeeklyPlanService._training_week(repo, "renato", CURRENT_WEEK_START)
        == 1
    )


def test_week_start_monday_to_saturday_is_current_week_monday():

    # segunda 20/07 até sábado 25/07 -> segunda 20/07
    for offset in range(6):  # seg..sab
        day = date(2026, 7, 20) + timedelta(days=offset)
        assert WeeklyPlanService._week_start(day) == date(2026, 7, 20)


def test_week_start_on_sunday_targets_next_monday():

    # domingo 26/07 é véspera: plano ESCRITO (print externo) é pra semana
    # que começa 27/07 — nunca a que está acabando
    assert (
        WeeklyPlanService._week_start(date(2026, 7, 26))
        == date(2026, 7, 27)
    )


def test_active_week_start_does_not_roll_on_sunday():

    # LEITURA: domingo 12/07 ainda é da semana ativa que começou seg 06/07
    # (ao contrário de _week_start, que adianta pra escrita/entrega)
    assert (
        WeeklyPlanService.active_week_start(date(2026, 7, 12))
        == date(2026, 7, 6)
    )
    # dia de semana: segunda da própria semana
    assert (
        WeeklyPlanService.active_week_start(date(2026, 7, 8))
        == date(2026, 7, 6)
    )


def test_upcoming_week_start_is_next_monday():

    # a entrega de domingo 15h mira a próxima semana (13/07), seja o
    # gatilho no domingo ou em outro dia da semana ativa
    assert (
        WeeklyPlanService.upcoming_week_start(date(2026, 7, 12))
        == date(2026, 7, 13)
    )
    assert (
        WeeklyPlanService.upcoming_week_start(date(2026, 7, 8))
        == date(2026, 7, 13)
    )


def test_sunday_read_keeps_active_week_and_does_not_generate():

    # Bug do Renato (domingo 12/07): a leitura da semana no domingo NÃO pode
    # gerar/mostrar o plano da próxima semana — devolve o da semana ATIVA
    # (06/07) sem gerar nada.
    with (
        patch(f"{MODULE}.WeeklyPlanRepository") as mock_repo_cls,
        patch(f"{MODULE}.TrainingPlanner") as mock_planner,
    ):

        active = _plan(date(2026, 7, 6))

        mock_repo = MagicMock()
        mock_repo.load.return_value = active
        mock_repo_cls.return_value = mock_repo

        result = WeeklyPlanService.get_or_generate(
            profile="renato",
            runner=make_runner(),
            assessment=object(),
            metrics=object(),
            goal=object(),
            reference_date=date(2026, 7, 12),  # domingo
        )

        assert result is active
        mock_planner.generate.assert_not_called()
        mock_repo.save.assert_not_called()


def test_read_keeps_future_delivered_plan_without_regenerating():

    # Depois da entrega de domingo 15h, o slot já tem a PRÓXIMA semana
    # (13/07). Uma leitura de domingo à tarde (semana ativa 06/07) não pode
    # regenerar a semana atual por cima do plano já entregue.
    with (
        patch(f"{MODULE}.WeeklyPlanRepository") as mock_repo_cls,
        patch(f"{MODULE}.TrainingPlanner") as mock_planner,
    ):

        delivered_next = _plan(date(2026, 7, 13))

        mock_repo = MagicMock()
        mock_repo.load.return_value = delivered_next
        mock_repo_cls.return_value = mock_repo

        result = WeeklyPlanService.get_or_generate(
            profile="renato",
            runner=make_runner(),
            assessment=object(),
            metrics=object(),
            goal=object(),
            reference_date=date(2026, 7, 12),  # domingo, semana ativa 06/07
        )

        assert result is delivered_next
        mock_planner.generate.assert_not_called()
        mock_repo.save.assert_not_called()


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
            runner=make_runner(),
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
            runner=make_runner(),
            assessment=object(),
            metrics=object(),
            goal=object(),
            reference_date=REFERENCE_DATE,
        )

        assert result is fresh

        mock_planner.generate.assert_called_once()

        # week_start e training_week são passados posicionalmente ao final
        assert (
            mock_planner.generate.call_args.args[-2] == CURRENT_WEEK_START
        )
        # sem histórico anterior: primeira semana de treino
        assert mock_planner.generate.call_args.args[-1] == 1

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
            runner=make_runner(),
            assessment=object(),
            metrics=object(),
            goal=object(),
            reference_date=REFERENCE_DATE,
        )

        assert result is fresh

        mock_repo.save.assert_called_once_with("renato", fresh)


def test_external_coach_reuses_stale_plan_and_never_generates():

    with (
        patch(f"{MODULE}.WeeklyPlanRepository") as mock_repo_cls,
        patch(f"{MODULE}.TrainingPlanner") as mock_planner,
    ):

        stale = _plan(CURRENT_WEEK_START.replace(day=1))
        stale.source = "externo"

        mock_repo = MagicMock()
        mock_repo.load.return_value = stale
        mock_repo_cls.return_value = mock_repo

        result = WeeklyPlanService.get_or_generate(
            profile="fulano",
            runner=make_runner(external_coach=True),
            assessment=object(),
            metrics=object(),
            goal=object(),
            reference_date=REFERENCE_DATE,
        )

        # acompanha o último plano enviado, mesmo de semana anterior
        assert result is stale

        mock_planner.generate.assert_not_called()
        mock_repo.save.assert_not_called()


def test_external_coach_without_plan_gets_empty_placeholder():

    with (
        patch(f"{MODULE}.WeeklyPlanRepository") as mock_repo_cls,
        patch(f"{MODULE}.TrainingPlanner") as mock_planner,
    ):

        mock_repo = MagicMock()
        mock_repo.load.return_value = None
        mock_repo_cls.return_value = mock_repo

        result = WeeklyPlanService.get_or_generate(
            profile="fulano",
            runner=make_runner(external_coach=True),
            assessment=object(),
            metrics=object(),
            goal=object(),
            reference_date=REFERENCE_DATE,
        )

        assert result.source == "externo"
        assert result.sessions == []
        assert result.week_start == CURRENT_WEEK_START

        mock_planner.generate.assert_not_called()
        # placeholder não é persistido
        mock_repo.save.assert_not_called()
