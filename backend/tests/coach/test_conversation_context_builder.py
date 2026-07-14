import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch

from app.application.coach.conversation.conversation_context_builder import (
    ConversationContextBuilder,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.training_assessment import TrainingAssessment
from app.domain.entities.training_history import TrainingHistory
from app.domain.entities.training_plan import TrainingPlan
from tests.coach.factories import make_activity, make_runner

MODULE = "app.application.coach.conversation.conversation_context_builder"


def _assessment(**overrides) -> TrainingAssessment:

    defaults = dict(
        level="Intermediate",
        current_weekly_volume=30.0,
        recommended_weekly_volume=32.4,
        consistency=82.0,
        longest_run=12.0,
        available_training_days=4,
        goal="10k",
        observations=[],
    )

    defaults.update(overrides)

    return TrainingAssessment(**defaults)


def _metrics(**overrides) -> RunnerMetrics:

    defaults = dict(
        easy_pace_min=5.20,
        easy_pace_max=5.80,
        threshold_pace=4.85,
        vo2_pace=4.35,
        average_hr=150.0,
        max_long_run=15.0,
        weekly_volume=30.0,
    )

    defaults.update(overrides)

    return RunnerMetrics(**defaults)


def _plan(sessions=None) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato",
        objective="10k",
        phase="base",
        weekly_volume=30.0,
        running_days=["Tuesday", "Thursday"],
        week_start=date(2026, 7, 20),
        sessions=sessions or [],
    )


async def _build_with_mocks(
    history_activities,
    sessions,
    memory="",
    summary="",
    lifetime_stats=None,
):

    with (
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load_runner,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_load_history,
        patch(f"{MODULE}.TrainingAssessmentBuilder") as mock_assessment_builder,
        patch(f"{MODULE}.MetricsResolver") as mock_metrics_resolver,
        patch(f"{MODULE}.WeeklyPlanService") as mock_plan_service,
        patch(f"{MODULE}.RunnerMemoryService") as mock_memory_service,
        patch(f"{MODULE}.ConversationRepository") as mock_conv_repo,
        patch(f"{MODULE}.ActivityArchiveRepository") as mock_archive,
    ):

        mock_load_runner.execute.return_value = make_runner()

        mock_load_history.execute = AsyncMock(
            return_value=TrainingHistory(activities=history_activities),
        )

        mock_assessment_builder.build.return_value = _assessment()

        mock_metrics_resolver.resolve.return_value = _metrics()

        mock_plan_service.get_or_generate.return_value = _plan(sessions)

        mock_memory_service.render.return_value = memory

        mock_conv_repo.return_value.load_summary.return_value = {
            "summary": summary,
            "covered_until": "",
        }

        mock_archive.return_value.stats.return_value = lifetime_stats

        return await ConversationContextBuilder.build("renato")


def test_build_includes_runner_facts_and_last_activity():

    activity = make_activity(distance=10500.0, name="Rodagem")

    text = asyncio.run(
        _build_with_mocks(
            history_activities=[activity],
            sessions=[],
        )
    )

    assert "Renato" in text
    assert "30.0 km" in text
    assert "32.4 km" in text
    assert "82%" in text
    assert "Rodagem, 10.5 km" in text


def test_build_anchors_today_date():
    """Sem a data de hoje, a IA adivinha o dia da semana e erra ('amanhã é
    sexta' num sábado). A âncora dá hoje/amanhã/ontem JÁ RESOLVIDOS pra a IA
    não calcular (bug real: domingo virou segunda deduzindo das datas do
    plano)."""

    from datetime import timedelta

    from app.core.clock import today_local
    from app.core.weekdays import weekday_label, weekday_name

    text = asyncio.run(_build_with_mocks(history_activities=[], sessions=[]))

    today = today_local()
    tomorrow = today + timedelta(days=1)
    yesterday = today - timedelta(days=1)

    # hoje, amanhã e ontem — todos com dia da semana + data explícitos
    assert "HOJE é" in text
    assert "AMANHÃ é" in text
    assert "ONTEM foi" in text
    for day in (today, tomorrow, yesterday):
        assert weekday_label(weekday_name(day)) in text
        assert day.strftime("%d/%m/%Y") in text
    # avisa pra não deduzir a data de hoje a partir do cronograma do plano
    assert "NUNCA recalcule" in text
    assert "datas do plano" in text


def test_build_includes_full_week_plan_when_sessions_exist():

    session = PlannedSession(
        day="Thursday",
        workout_type="Intervalado",
        objective="Velocidade",
        planned_distance_km=8.0,
        planned_duration_minutes=45,
        target_pace_min="4:21",
        target_pace_max="4:21",
    )

    text = asyncio.run(
        _build_with_mocks(
            history_activities=[],
            sessions=[session],
        )
    )

    assert "Plano da semana completo:" in text
    assert "quinta-feira" in text
    assert "8.0 km" in text


def test_build_omits_week_plan_without_sessions():

    text = asyncio.run(
        _build_with_mocks(
            history_activities=[],
            sessions=[],
        )
    )

    assert "Plano da semana completo" not in text


def test_build_includes_conversation_summary_when_present():

    text = asyncio.run(
        _build_with_mocks(
            history_activities=[],
            sessions=[],
            summary="Discutiram estratégia de pace para a prova de outubro.",
        )
    )

    assert (
        "Resumo de conversas anteriores: Discutiram estratégia" in text
    )


def test_build_includes_lifetime_stats_when_archive_has_data():

    text = asyncio.run(
        _build_with_mocks(
            history_activities=[],
            sessions=[],
            lifetime_stats={
                "total_runs": 123,
                "total_km": 861.4,
                "first_date": "2025-03-14",
                "longest_km": 21.1,
            },
        )
    )

    assert "Histórico geral registrado: 123 treinos" in text
    assert "861 km desde 03/2025" in text
    assert "maior treino: 21.1 km" in text


def test_build_omits_summary_and_lifetime_when_empty():

    text = asyncio.run(
        _build_with_mocks(
            history_activities=[],
            sessions=[],
        )
    )

    assert "Resumo de conversas anteriores" not in text
    assert "Histórico geral" not in text


def test_build_includes_memory_section_when_present():

    text = asyncio.run(
        _build_with_mocks(
            history_activities=[],
            sessions=[],
            memory=(
                "Memória do corredor (fatos anotados de conversas anteriores):\n"
                "- [lesao] Dor no joelho direito (01/07)"
            ),
        )
    )

    assert "Memória do corredor" in text
    assert "[lesao] Dor no joelho direito" in text


def test_build_has_no_memory_section_when_empty():

    text = asyncio.run(
        _build_with_mocks(
            history_activities=[],
            sessions=[],
            memory="",
        )
    )

    assert "Memória do corredor" not in text


def test_build_handles_no_recent_activity():

    text = asyncio.run(
        _build_with_mocks(
            history_activities=[],
            sessions=[],
        )
    )

    assert "nenhum treino recente encontrado" in text


def test_next_session_summary_includes_real_date_and_pace():

    session = PlannedSession(
        day="Thursday",
        workout_type="Intervalado",
        objective="Velocidade",
        planned_distance_km=8.0,
        planned_duration_minutes=45,
        target_pace_min="4:21",
        target_pace_max="4:21",
    )

    plan = _plan([session])

    summary = ConversationContextBuilder._next_session_summary(
        plan,
        TrainingHistory(activities=[]),
        reference_date=date(2026, 7, 20),
    )

    assert "quinta-feira" in summary
    assert "23/07" in summary  # quinta-feira da semana de 2026-07-20
    assert "Intervalado" in summary
    assert "8.0 km" in summary
    assert "4:21-4:21" in summary


def test_next_session_summary_flags_today():
    """Sessão de hoje vem marcada [É HOJE] — sem isso o modelo lê "próximo
    treino ... 14/07" e chama de "amanhã" (bug real do Renato)."""

    session = PlannedSession(
        day="Monday", workout_type="Velocidade", objective="tiros",
        planned_distance_km=8.0, planned_duration_minutes=None,
        target_pace_min="5:15", target_pace_max="5:30",
    )

    plan = _plan([session])  # week_start = segunda 2026-07-20

    summary = ConversationContextBuilder._next_session_summary(
        plan,
        TrainingHistory(activities=[]),
        reference_date=date(2026, 7, 20),  # a própria segunda
    )

    assert "[É HOJE]" in summary


def test_next_session_summary_flags_tomorrow():

    session = PlannedSession(
        day="Tuesday", workout_type="Velocidade", objective="tiros",
        planned_distance_km=8.0, planned_duration_minutes=None,
        target_pace_min="5:15", target_pace_max="5:30",
    )

    plan = _plan([session])  # terça = 2026-07-21

    summary = ConversationContextBuilder._next_session_summary(
        plan,
        TrainingHistory(activities=[]),
        reference_date=date(2026, 7, 20),  # segunda: a terça é amanhã
    )

    assert "[É AMANHÃ]" in summary


def test_next_session_summary_no_today_flag_for_future_session():

    session = PlannedSession(
        day="Thursday", workout_type="Intervalado", objective="VO2",
        planned_distance_km=8.0, planned_duration_minutes=None,
        target_pace_min="4:21", target_pace_max="4:21",
    )

    plan = _plan([session])  # quinta = 2026-07-23

    summary = ConversationContextBuilder._next_session_summary(
        plan,
        TrainingHistory(activities=[]),
        reference_date=date(2026, 7, 20),
    )

    assert "[É HOJE]" not in summary
    assert "[É AMANHÃ]" not in summary


def test_next_session_summary_includes_adjustment_reason_when_present():

    session = PlannedSession(
        day="Thursday",
        workout_type="Easy Run",
        objective="Base",
        planned_distance_km=8.0,
        planned_duration_minutes=None,
        target_pace_min="5:20",
        target_pace_max="5:50",
        adjusted=True,
        adjustment_reason="Reduzido de 10.0 km para 8.0 km: carga alta.",
    )

    plan = _plan([session])

    summary = ConversationContextBuilder._next_session_summary(
        plan,
        TrainingHistory(activities=[]),
        reference_date=date(2026, 7, 20),
    )

    assert "AJUSTADO" in summary
    assert "Reduzido de 10.0 km para 8.0 km" in summary


def test_next_session_summary_picks_closest_upcoming_not_first():

    past_session = PlannedSession(
        day="Monday",
        workout_type="Easy Run",
        objective="Base",
        planned_distance_km=6.0,
        planned_duration_minutes=None,
        target_pace_min="5:20",
        target_pace_max="5:50",
    )

    future_session = PlannedSession(
        day="Sunday",
        workout_type="Long Run",
        objective="Resistência",
        planned_distance_km=15.0,
        planned_duration_minutes=None,
        target_pace_min="5:20",
        target_pace_max="5:50",
    )

    plan = _plan([past_session, future_session])

    # reference_date cai numa quarta — a segunda já passou, o próximo é domingo
    summary = ConversationContextBuilder._next_session_summary(
        plan,
        TrainingHistory(activities=[]),
        reference_date=date(2026, 7, 22),
    )

    assert "domingo" in summary
    assert "Long Run" in summary


def test_next_session_summary_no_past_fallback():
    """Todas as sessões já passaram: não devolve uma data passada como
    "próximo treino" — avisa que não há treino restante."""

    plan = _plan([
        PlannedSession(
            day="Monday", workout_type="Easy Run", objective="Base",
            planned_distance_km=6.0, planned_duration_minutes=None,
            target_pace_min=None, target_pace_max=None,
        ),
        PlannedSession(
            day="Wednesday", workout_type="Intervalado", objective="VO2",
            planned_distance_km=8.0, planned_duration_minutes=None,
            target_pace_min=None, target_pace_max=None,
        ),
    ])

    summary = ConversationContextBuilder._next_session_summary(
        plan,
        TrainingHistory(activities=[]),
        reference_date=date(2026, 7, 25),  # sábado, tudo já passou
    )

    assert "sem treino planejado restante" in summary
    assert "22/07" not in summary  # não recita a data passada


def test_week_plan_summary_flags_ended_week_for_stale_plan():
    """Plano de semana já encerrada (ex.: externo não renovado): marca as
    datas como passadas, pra o coach não recitar como semana atual."""

    session = PlannedSession(
        day="Tuesday", workout_type="Caminhada com corrida",
        objective="HIIT 2x2k", planned_distance_km=5.0,
        planned_duration_minutes=None,
        target_pace_min=None, target_pace_max=None,
    )

    stale_plan = TrainingPlan(
        athlete_name="Mauricio", objective="21k", phase="EXTERNO",
        weekly_volume=5.0, running_days=["Tuesday"],
        week_start=date(2020, 1, 6),  # semana bem no passado
        sessions=[session], source="externo",
    )

    text = ConversationContextBuilder._week_plan_summary(
        stale_plan,
        TrainingHistory(activities=[]),
    )

    assert "JÁ ENCERRADA" in text
    assert "aguardando o print do plano desta semana" in text


def test_build_handles_no_planned_sessions():

    text = asyncio.run(
        _build_with_mocks(
            history_activities=[],
            sessions=[],
        )
    )

    assert "nenhum treino planejado ainda" in text


def test_race_summary_includes_countdown_and_target():

    from app.domain.entities.training_goal import TrainingGoal

    goal = TrainingGoal(
        name="10 km Sub 50",
        distance_km=10.0,
        target_time="00:50:00",
        race_date=date(2026, 8, 15),
    )

    line = ConversationContextBuilder._race_summary(
        goal,
        reference_date=date(2026, 7, 3),
    )

    assert "Prova alvo: 10 km Sub 50 em 15/08/2026" in line
    assert "daqui a 6 semanas" in line
    assert "alvo 00:50:00" in line


def test_race_summary_empty_without_race_or_past_race():

    from app.domain.entities.training_goal import TrainingGoal

    no_race = TrainingGoal(
        name="Saúde", distance_km=10.0,
        target_time=None, race_date=None,
    )

    past_race = TrainingGoal(
        name="10k", distance_km=10.0,
        target_time=None, race_date=date(2026, 6, 1),
    )

    assert ConversationContextBuilder._race_summary(
        no_race, reference_date=date(2026, 7, 3),
    ) == ""

    assert ConversationContextBuilder._race_summary(
        past_race, reference_date=date(2026, 7, 3),
    ) == ""
