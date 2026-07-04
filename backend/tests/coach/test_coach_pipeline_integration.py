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
    assert "Ritmo: 5:00 min/km" in text


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

    assert "registrei como treino extra" in text
