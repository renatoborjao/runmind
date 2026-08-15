"""Compõe a estratégia de prova em treino GUIADO e empurra pro Garmin, agendado
na data da prova e PROTEGIDO do sweep. Reusável: companheiro de prova (oferta na
semana) e on-demand. Devolve o resultado do push, ou None se não dá pra montar
(sem prova/distância/forma). Ver [[RaceWorkoutComposer]]."""

from app.application.coach.planning.race_strategy_engine import (
    RaceStrategyEngine,
)
from app.application.coach.planning.race_workout_composer import (
    RaceWorkoutComposer,
)
from app.application.garmin.garmin_push import push_session
from app.application.history.metrics_resolver import MetricsResolver
from app.application.planner.pace_formatter import PaceFormatter
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import LoadTrainingHistory
from app.domain.entities.planned_session import PlannedSession
from app.infrastructure.persistence.protected_workout_store import (
    ProtectedWorkoutStore,
)


async def push_race_workout(profile: str) -> dict | None:
    """Monta e empurra o treino de prova. None quando não há prova com data +
    distância, ou não dá pra estimar a forma."""

    runner = LoadRunnerProfile.execute(profile)

    goal = BuildTrainingGoal.execute(runner)

    if goal.race_date is None or not goal.distance_km:

        return None

    history = await LoadTrainingHistory.execute(profile=profile)

    metrics = MetricsResolver.resolve(runner, history)

    plan = RaceStrategyEngine.plan(goal, metrics)

    if plan is None:

        return None

    steps = RaceWorkoutComposer.compose(plan)

    if not steps:

        return None

    avg = PaceFormatter.format(plan.avg_pace_min)

    structure = "Negative split (segura o começo, fecha forte):\n" + "\n".join(
        f"• {s.distance_m / 1000:.0f} km @ {s.pace_min}-{s.pace_max}/km"
        for s in steps
    )

    session = PlannedSession(
        day=goal.race_date.strftime("%A"),
        workout_type="RACE",
        objective=f"Prova {goal.race_label}",
        planned_distance_km=goal.distance_km,
        planned_duration_minutes=None,
        target_pace_min=avg,
        target_pace_max=avg,
        steps=steps,
        kind="run",
        origin="oneoff",
        purpose=(
            f"Prova {goal.race_label}. Segura os primeiros km; feche forte."
        ),
        structure=structure,
    )

    result = push_session(profile, session, goal.race_date)

    if result.get("ok") and result.get("workout_id"):

        ProtectedWorkoutStore().add(profile, result["workout_id"])

    return result
