from app.application.coach.context.coach_context_builder import (
    CoachContextBuilder,
)
from app.application.coach.pipeline.coach_pipeline import (
    CoachPipeline,
)
from app.application.coach.summary.coach_summary_builder import (
    CoachSummaryBuilder,
)
from app.application.coach.writer.coach_writer import (
    CoachWriter,
)
from app.application.coach.writer.whatsapp_formatter import (
    WhatsAppFormatter,
)
from app.domain.entities.training_assessment import (
    TrainingAssessment,
)
from app.domain.entities.training_history import (
    TrainingHistory,
)
from tests.coach.factories import (
    make_activity,
    make_enriched_activity,
    make_planned_session,
    make_runner,
)


def test_full_chain_produces_final_whatsapp_message():

    runner = make_runner(name="Renato")

    planned = make_planned_session(
        workout_type="Rodagem Leve",
        planned_distance_km=10.0,
    )

    executed = make_enriched_activity(
        activity=make_activity(distance=11500.0),
        training_type="RODAGEM",
        intensity="HIGH",
        pace_min_km=5.0,
        recovery_hours=40,
        fatigue_score=60,
    )

    history = TrainingHistory(activities=[executed.activity])

    assessment = TrainingAssessment(
        level="Intermediate",
        current_weekly_volume=30.0,
        recommended_weekly_volume=32.4,
        consistency=82,
        longest_run=12.0,
        available_training_days=4,
        goal="10k",
        observations=[],
    )

    context = CoachContextBuilder.build(
        runner=runner,
        planned=planned,
        executed=executed,
        history=history,
        assessment=assessment,
    )

    analysis = CoachPipeline.execute(context)

    summary = CoachSummaryBuilder.build(runner.name, analysis)

    message = CoachWriter.write(context, summary)

    text = WhatsAppFormatter.format(message)

    assert "Renato" in text

    assert "15%" in text

    assert (
        "Sua carga foi significativa"
        not in text
    )  # sanity: nenhuma frase inventada fora do phrasebook

    assert "A carga foi significativa, mas dentro do esperado." in text

    # sem próxima sessão no contexto = semana concluída: nada de "amanhã"
    assert "Priorize recuperação ativa nos próximos dias." in text

    assert "amanhã" not in text

    assert (
        "Semana concluída — aproveite o descanso; "
        "retomamos no próximo plano." in text
    )

    # exibição em pt-BR: sem enums crus
    assert "Intensidade: Alta" in text
    assert "HIGH" not in text
    assert "Ritmo médio: 5:00 min/km" in text


def test_weekly_volume_uses_current_iso_week_not_4wk_average():
    """Bug do Renato (12/07): o progresso de volume vinha da média de 4
    semanas contra 1.08x ela mesma -> ~92% fixo ("próximo de concluir")
    mesmo num treino extra com a semana já fechada. Agora conta os km REAIS
    da semana ISO do treino executado; a média histórica não entra."""

    from datetime import datetime

    def _run(day, km):
        return make_activity(
            id=day,
            start_date=datetime(2026, 7, day, 7, 0, 0),
            distance=km * 1000,
        )

    # semana ISO anterior (não deve contar) + a semana atual (6–12/07)
    prev_week = _run(1, 10.0)              # 01/07, semana passada
    this_week = [
        _run(7, 8.0),                     # ter 07/07
        _run(9, 8.0),                     # qui 09/07
        _run(11, 10.0),                   # sáb 11/07
    ]
    extra = _run(12, 5.0)                 # dom 12/07, corrida extra

    executed = make_enriched_activity(
        activity=extra,
        training_type="EASY",
        intensity="LOW",
        pace_min_km=6.5,
    )

    history = TrainingHistory(
        activities=[prev_week, *this_week, extra],
    )

    context = CoachContextBuilder.build(
        runner=make_runner(name="Renato"),
        planned=None,
        executed=executed,
        history=history,
        assessment=_base_assessment(),  # média/4sem = 30.0 (não deve vazar)
    )

    # só a semana ISO do treino executado: 8+8+10+5 = 31 (sem os 10 da
    # semana passada, sem a média de 4 semanas)
    assert context.weekly_volume == 31.0


def test_weekly_goal_uses_prescribed_plan_volume_not_history_average():
    """Bug do dry-run (atleta novo): com só a semana atual no histórico, a
    média ×1.08 vira ~92% fixo ("próximo de concluir") mesmo tendo feito 1 de
    3 treinos. A meta passa a ser o volume PRESCRITO do plano."""

    from datetime import datetime

    new_run = make_activity(
        id=1, distance=5000.0,
        start_date=datetime(2026, 7, 13, 7, 0, 0),
    )
    executed = make_enriched_activity(
        activity=new_run, training_type="EASY", pace_min_km=6.0,
    )

    context = CoachContextBuilder.build(
        runner=make_runner(name="Joao"),
        planned=None,
        executed=executed,
        history=TrainingHistory(activities=[new_run]),
        assessment=_base_assessment(),      # recommended = 32.4
        plan_weekly_volume=15.0,            # prescrito da semana
    )

    # meta = prescrito (15), não a média histórica (32.4); 5/15 = 33% (em
    # andamento), não os 92% degenerados
    assert context.weekly_goal == 15.0
    assert context.weekly_volume == 5.0


def _base_assessment() -> TrainingAssessment:

    return TrainingAssessment(
        level="Intermediate",
        current_weekly_volume=30.0,
        recommended_weekly_volume=32.4,
        consistency=82,
        longest_run=12.0,
        available_training_days=4,
        goal="10k",
        observations=[],
    )


def test_unplanned_workout_skips_plan_comparison():

    runner = make_runner(name="Renato")

    executed = make_enriched_activity(
        activity=make_activity(distance=5000.0),
        training_type="EASY",
        intensity="LOW",
        pace_min_km=6.5,
    )

    history = TrainingHistory(activities=[executed.activity])

    context = CoachContextBuilder.build(
        runner=runner,
        planned=None,
        executed=executed,
        history=history,
        assessment=_base_assessment(),
    )

    analysis = CoachPipeline.execute(context)

    assert analysis.distance is None
    assert analysis.type_match is None
    assert analysis.unplanned is not None

    summary = CoachSummaryBuilder.build(runner.name, analysis)

    message = CoachWriter.write(context, summary)

    text = WhatsAppFormatter.format(message)

    # sem seção "Planejado" e sem comparação com o plano
    assert "Planejado" not in text
    assert "distância planejada" not in text
    assert "acima da distância" not in text

    assert "Treino extra, ótimo — todo movimento conta!" in text
