"""Geração do PRIMEIRO plano de um atleta recém-cadastrado, a partir do retrato
real (histórico do Strava se já conectou, senão inicial conservador). É o mesmo
miolo pro onboarding do bot (Telegram) e pro wizard do app — a inteligência mora
num lugar só. Ver [[project_track_a_plano_fiel]] e [[project_modelo_pace_vdot]].
"""

from __future__ import annotations

from datetime import timedelta

from app.application.assessment.training_assessment_builder import (
    TrainingAssessmentBuilder,
)
from app.application.coach.planning.ai_plan_service import AIPlanService
from app.application.history.metrics_resolver import MetricsResolver
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.application.use_cases.load_training_history import LoadTrainingHistory
from app.core.clock import today_local
from app.domain.entities.training_history import TrainingHistory
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


async def ensure_initial_plan(slug: str, start_next_week: bool = False):
    """Monta (e persiste) o plano inicial do atleta. Devolve
    `(plan, runner, history, reference_date)` pra quem chama poder formatar
    mensagem / leitura de boas-vindas sem recarregar tudo.

    A IA-treinadora gera a partir do retrato real; run/walk, treinador externo
    e falha da IA caem no determinístico (dentro de `AIPlanService`)."""

    repository = RunnerProfileRepository()

    runner = repository.load(slug)

    try:

        history = await LoadTrainingHistory.execute(profile=slug)

    except Exception:

        # sem Strava conectado ainda: plano inicial conservador
        history = TrainingHistory(activities=[])

    assessment = TrainingAssessmentBuilder.build(runner, history)

    metrics = MetricsResolver.resolve(runner, history)

    goal = BuildTrainingGoal.execute(runner)

    today = today_local()

    if start_next_week:

        monday = today - timedelta(days=today.weekday())

        reference_date = monday + timedelta(days=7)

    else:

        reference_date = today

    plan = await AIPlanService.ensure_plan(
        profile=slug,
        runner=runner,
        assessment=assessment,
        metrics=metrics,
        goal=goal,
        history=history,
        reference_date=reference_date,
    )

    return plan, runner, history, reference_date
