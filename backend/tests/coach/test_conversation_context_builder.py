import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

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


def _plan(sessions=None, week_start=date(2026, 7, 20)) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato",
        objective="10k",
        phase="base",
        weekly_volume=30.0,
        running_days=["Tuesday", "Thursday"],
        week_start=week_start,
        sessions=sessions or [],
    )


def _current_week_start() -> date:
    """Segunda-feira da semana de HOJE. Os testes que passam por
    `_build_with_mocks` batem contra o relógio real (o builder chama
    today_local por dentro) — plano com data fixa vira teste que expira."""

    from app.core.clock import today_local

    today = today_local()

    return today - timedelta(days=today.weekday())


async def _build_with_mocks(
    history_activities,
    sessions,
    dossier="DOSSIÊ-DO-ATLETA",
    pending_rpe="",
):

    with (
        patch(f"{MODULE}.LoadRunnerProfile") as mock_load_runner,
        patch(f"{MODULE}.LoadTrainingHistory") as mock_load_history,
        patch(f"{MODULE}.TrainingAssessmentBuilder") as mock_assessment_builder,
        patch(f"{MODULE}.MetricsResolver") as mock_metrics_resolver,
        patch(f"{MODULE}.WeeklyPlanService") as mock_plan_service,
        patch(
            "app.application.coach.context.athlete_dossier.AthleteDossier.render",
            return_value=dossier,
        ) as mock_dossier,
        patch(
            "app.application.coach.intelligence.perception_recorder."
            "PerceptionRecorder.pending_line",
            return_value=pending_rpe,
        ),
    ):

        mock_load_runner.execute.return_value = make_runner()

        mock_load_history.execute = AsyncMock(
            return_value=TrainingHistory(activities=history_activities),
        )

        mock_assessment_builder.build.return_value = _assessment()

        mock_metrics_resolver.resolve.return_value = _metrics()

        mock_plan_service.get_or_generate.return_value = _plan(
            sessions,
            week_start=_current_week_start(),
        )

        text = await ConversationContextBuilder.build("renato")

        _build_with_mocks.dossier_call = mock_dossier.call_args

        return text


def test_build_includes_last_activity_and_the_dossier():
    """O chat monta SÓ o que é dele (datas, último/próximo treino, status de
    hoje) e o resto vem do DOSSIÊ — a mesma base do plano e da análise."""

    activity = make_activity(distance=10500.0, name="Rodagem")

    text = asyncio.run(
        _build_with_mocks(
            history_activities=[activity],
            sessions=[],
        )
    )

    assert "Rodagem, 10.5 km" in text
    assert "DOSSIÊ-DO-ATLETA" in text


def test_dossier_gets_the_same_runner_history_and_plan_objects():
    """Mesmo objeto = mesma verdade: o dossiê não recarrega por outro caminho
    o plano/histórico que o chat já tem."""

    activity = make_activity(distance=8000.0)

    asyncio.run(_build_with_mocks(history_activities=[activity], sessions=[]))

    kwargs = _build_with_mocks.dossier_call.kwargs

    assert kwargs["history"].activities == [activity]
    assert kwargs["plan"] is not None
    assert kwargs["runner"] is not None


def test_pending_rpe_question_reaches_the_brain():
    """Pergunta de esforço em aberto: uma resposta em PALAVRAS é a resposta a
    ela — o cérebro precisa saber pra gravar a percepção."""

    text = asyncio.run(
        _build_with_mocks(
            history_activities=[],
            sessions=[],
            pending_rpe="PERGUNTA EM ABERTO: esforço do treino de 26/09",
        )
    )

    assert "PERGUNTA EM ABERTO" in text


def test_build_handles_no_recent_activity():

    text = asyncio.run(
        _build_with_mocks(
            history_activities=[],
            sessions=[],
        )
    )

    assert "nenhum treino recente encontrado" in text


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


def test_week_calendar_resolves_every_weekday_and_marks_past():
    """Bug do Renato: pediu 'amanhã→sexta' (numa quarta) e o coach propôs
    'terça' (dia que já passou). O calendário resolve TODO dia com data e
    marca o que já passou, pra a IA nunca chutar nem propor dia vencido."""

    # quarta-feira
    cal = ConversationContextBuilder._week_calendar(date(2026, 8, 5))

    # o dia pedido ("sexta") vem resolvido com a data certa
    assert "sexta-feira 07/08" in cal
    # terça já passou nesta semana — marcada, pra não ser proposta
    assert "terça-feira 04/08 (já passou)" in cal
    # hoje e amanhã marcados
    assert "quarta-feira 05/08 ← HOJE" in cal
    assert "quinta-feira 06/08 ← amanhã" in cal
    # a próxima semana também entra (pra "sexta que vem")
    assert "Próxima semana:" in cal
    assert "sexta-feira 14/08" in cal


def test_week_calendar_present_in_facts():

    text = asyncio.run(_build_with_mocks(history_activities=[], sessions=[]))

    assert "CALENDÁRIO" in text
    assert "NUNCA proponha um dia que JÁ PASSOU" in text


def test_today_status_marks_concluded_when_fulfilled():
    """Treino de hoje já cumprido: o coach precisa saber que ACABOU (e foi
    analisado), pra não tratar o atleta como se estivesse no meio da sessão."""

    session = PlannedSession(
        day="Monday", workout_type="Velocidade", objective="tiros",
        planned_distance_km=8.0, planned_duration_minutes=None,
        target_pace_min="5:15", target_pace_max="5:30",
    )

    plan = _plan([session])  # week_start = segunda 2026-07-20

    with patch(f"{MODULE}.WeeklyPlanMatcher") as matcher:

        matcher.fulfilled_days.return_value = {"Monday"}

        status = ConversationContextBuilder._today_training_status(
            plan,
            TrainingHistory(activities=[]),
            reference_date=date(2026, 7, 20),
        )

    assert "JÁ CONCLUÍDO" in status
    assert "no meio" in status  # regra explícita pro coach


def test_today_status_pending_when_not_fulfilled():

    session = PlannedSession(
        day="Monday", workout_type="Velocidade", objective="tiros",
        planned_distance_km=8.0, planned_duration_minutes=None,
        target_pace_min="5:15", target_pace_max="5:30",
    )

    plan = _plan([session])

    with patch(f"{MODULE}.WeeklyPlanMatcher") as matcher:

        matcher.fulfilled_days.return_value = set()

        status = ConversationContextBuilder._today_training_status(
            plan,
            TrainingHistory(activities=[]),
            reference_date=date(2026, 7, 20),
        )

    assert "ainda NÃO registrado" in status


def test_today_status_empty_on_rest_day():
    """Hoje é descanso (sessão só na quinta): sem linha de status."""

    session = PlannedSession(
        day="Thursday", workout_type="Rodagem", objective="base",
        planned_distance_km=9.0, planned_duration_minutes=None,
        target_pace_min="6:30", target_pace_max="7:00",
    )

    plan = _plan([session])

    status = ConversationContextBuilder._today_training_status(
        plan,
        TrainingHistory(activities=[]),
        reference_date=date(2026, 7, 20),  # segunda: nada planejado
    )

    assert status == ""


def test_last_activity_summary_flags_today():

    act = make_activity(
        name="Corrida da tarde",
        distance=6000.0,
        start_date=datetime(2026, 7, 20, 16, 0),
    )

    summary = ConversationContextBuilder._last_activity_summary(
        TrainingHistory(activities=[act]),
        reference_date=date(2026, 7, 20),
    )

    assert "(HOJE)" in summary
    assert "6.0 km" in summary


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


def test_build_handles_no_planned_sessions():

    text = asyncio.run(
        _build_with_mocks(
            history_activities=[],
            sessions=[],
        )
    )

    assert "nenhum treino planejado ainda" in text


# ---- grounding do armário de tênis (mata o "Corre 4") ---------------------


def _armario_book():

    from app.domain.entities.shoe import Shoe, ShoeBook

    return ShoeBook(shoes=[
        Shoe(id="vomero", name="Vomero Plus", category="dia a dia",
             is_default=True, initial_km=200.0),
        Shoe(id="sonic", name="SonicBlast", category="versÃ¡til"),  # mojibake
    ])


def _shoe_armario(text):

    repo = MagicMock()
    repo.load.return_value = _armario_book()

    with patch(
        "app.infrastructure.persistence.shoe_repository.ShoeRepository",
        return_value=repo,
    ):

        return ConversationContextBuilder._shoe_armario("renato", text)


def test_shoe_armario_injects_real_shoes_when_asked():

    out = _shoe_armario("que tênis uso no tiro?")

    assert "SonicBlast" in out and "Vomero Plus" in out
    assert "versátil" in out          # mojibake curado no grounding
    assert "ÚNICOS" in out            # trava anti-alucinação
    assert "par padrão" in out


def test_shoe_armario_triggers_on_shoe_name_even_without_keyword():

    out = _shoe_armario("o sonicblast é bom pra longão?")

    assert "SonicBlast" in out


def test_shoe_armario_silent_when_off_topic():

    assert _shoe_armario("como foi meu treino de ontem?") == ""


def test_shoe_armario_silent_without_shoes():

    repo = MagicMock()
    repo.load.return_value.active.return_value = []

    with patch(
        "app.infrastructure.persistence.shoe_repository.ShoeRepository",
        return_value=repo,
    ):

        assert ConversationContextBuilder._shoe_armario("renato", "meus tênis") == ""
