"""Traduz uma PlannedSession num treino estruturado do Garmin.

Fonte de verdade = `session.steps` (passos que a IA-treinadora desenhou:
aquecimento, séries que repetem, recuperação, tempo, desaquecimento — com
alvo de pace ou FC). Isso cobre QUALQUER treino que o Garmin aceita, não só
tiros de 800m. Sem passos (plano externo, IA antiga), cai no fallback: um
passo por distância + faixa de pace."""

from garminconnect.workout import (
    ConditionType,
    ExecutableStep,
    RepeatGroup,
    RunningWorkout,
    StepType,
    TargetType,
    WalkingWorkout,
    WorkoutSegment,
    create_repeat_group,
)

from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.workout_step import (
    COOLDOWN,
    INTERVAL,
    RECOVERY,
    REST,
    RUN,
    WARMUP,
    WorkoutStep,
)

_RUNNING_SPORT = {
    "sportTypeId": 1,
    "sportTypeKey": "running",
    "displayOrder": 1,
}

# kind do passo -> (stepTypeId, stepTypeKey, displayOrder)
_STEP_TYPE = {
    WARMUP: (StepType.WARMUP, "warmup", 1),
    COOLDOWN: (StepType.COOLDOWN, "cooldown", 2),
    INTERVAL: (StepType.INTERVAL, "interval", 3),
    RUN: (StepType.INTERVAL, "interval", 3),
    RECOVERY: (StepType.RECOVERY, "recovery", 4),
    REST: (StepType.REST, "rest", 5),
}


def _pace_to_speed_ms(pace: str | None) -> float | None:
    """'4:45' (min:seg/km) -> velocidade em m/s (como o Garmin guarda pace)."""

    if not pace:

        return None

    try:

        minutes, seconds = pace.strip().split(":")

        total = int(minutes) * 60 + int(seconds)

        return round(1000 / total, 3) if total > 0 else None

    except (ValueError, AttributeError):

        return None


def _end_condition(step: WorkoutStep) -> tuple[dict, float | None]:
    """Como o passo termina: distância, tempo, ou aberto (botão lap)."""

    if step.distance_m:

        return (
            {
                "conditionTypeId": ConditionType.DISTANCE,
                "conditionTypeKey": "distance",
                "displayOrder": 3,
                "displayable": True,
            },
            float(step.distance_m),
        )

    if step.duration_sec:

        return (
            {
                "conditionTypeId": ConditionType.TIME,
                "conditionTypeKey": "time",
                "displayOrder": 2,
                "displayable": True,
            },
            float(step.duration_sec),
        )

    # sem distância nem tempo: avança quando o atleta aperta lap
    return (
        {
            "conditionTypeId": ConditionType.LAP_BUTTON,
            "conditionTypeKey": "lap.button",
            "displayOrder": 1,
            "displayable": True,
        },
        None,
    )


def _target(step: WorkoutStep) -> dict:
    """Alvo do passo (entra como campos extras no ExecutableStep): faixa de
    pace (guardada em m/s), faixa de FC (bpm), ou nenhum."""

    speed_fast = _pace_to_speed_ms(step.pace_min)

    speed_slow = _pace_to_speed_ms(step.pace_max)

    if speed_fast and speed_slow:

        return {
            "targetType": {
                "workoutTargetTypeId": TargetType.PACE_ZONE,
                "workoutTargetTypeKey": "pace.zone",
                "displayOrder": 6,
            },
            "targetValueOne": min(speed_slow, speed_fast),
            "targetValueTwo": max(speed_slow, speed_fast),
        }

    if step.hr_min and step.hr_max:

        return {
            "targetType": {
                "workoutTargetTypeId": TargetType.HEART_RATE_ZONE,
                "workoutTargetTypeKey": "heart.rate.zone",
                "displayOrder": 4,
            },
            "targetValueOne": float(min(step.hr_min, step.hr_max)),
            "targetValueTwo": float(max(step.hr_min, step.hr_max)),
        }

    return {
        "targetType": {
            "workoutTargetTypeId": TargetType.NO_TARGET,
            "workoutTargetTypeKey": "no.target",
            "displayOrder": 1,
        }
    }


class _Order:
    """stepOrder tem que ser sequencial no treino inteiro, inclusive dentro
    das repetições."""

    def __init__(self) -> None:

        self.value = 0

    def next(self) -> int:

        self.value += 1

        return self.value


def _executable(step: WorkoutStep, order: int) -> ExecutableStep:

    type_id, type_key, type_order = _STEP_TYPE.get(
        step.kind, (StepType.INTERVAL, "interval", 3)
    )

    end_condition, end_value = _end_condition(step)

    kwargs = {
        "stepOrder": order,
        "stepType": {
            "stepTypeId": type_id,
            "stepTypeKey": type_key,
            "displayOrder": type_order,
        },
        "endCondition": end_condition,
        "endConditionValue": end_value,
        **_target(step),
    }

    return ExecutableStep(**kwargs)


def _build_steps(
    steps: list[WorkoutStep],
    order: _Order,
) -> list[ExecutableStep | RepeatGroup]:

    built: list[ExecutableStep | RepeatGroup] = []

    for step in steps:

        if step.is_repeat:

            group_order = order.next()

            children = _build_steps(step.steps, order)

            built.append(
                create_repeat_group(
                    iterations=step.reps or 1,
                    workout_steps=children,
                    step_order=group_order,
                )
            )

        else:

            built.append(_executable(step, order.next()))

    return built


def _fallback_steps(session: PlannedSession) -> list[WorkoutStep]:
    """Sem passos estruturados: um bloco de corrida por distância, com pace
    se houver. Mantém o comportamento antigo pra planos externos/IA antiga."""

    meters = (session.planned_distance_km or 0) * 1000

    return [
        WorkoutStep(
            kind=RUN,
            distance_m=meters or None,
            pace_min=session.target_pace_min,
            pace_max=session.target_pace_max,
        )
    ]


def _estimated_seconds(steps: list[WorkoutStep]) -> int:
    """Palpite de duração pra preencher o campo do Garmin."""

    def leaf_seconds(step: WorkoutStep, multiplier: int = 1) -> int:

        if step.is_repeat:

            inner = sum(leaf_seconds(s) for s in step.steps)

            return inner * (step.reps or 1)

        if step.duration_sec:

            return step.duration_sec * multiplier

        if step.distance_m:

            fast = _pace_to_speed_ms(step.pace_min)

            slow = _pace_to_speed_ms(step.pace_max)

            speeds = [s for s in (fast, slow) if s]

            avg = sum(speeds) / len(speeds) if speeds else 2.78

            return int(step.distance_m / avg)

        return 0

    return sum(leaf_seconds(s) for s in steps)


class GarminWorkoutBuilder:

    @staticmethod
    def build(
        session: PlannedSession,
        name: str,
        description: str = "",
    ) -> RunningWorkout | WalkingWorkout:

        steps = session.steps or _fallback_steps(session)

        segment = WorkoutSegment(
            segmentOrder=1,
            sportType=_RUNNING_SPORT,
            workoutSteps=_build_steps(steps, _Order()),
        )

        workout_cls = (
            WalkingWorkout if session.kind == "walk" else RunningWorkout
        )

        return workout_cls(
            workoutName=name,
            estimatedDurationInSecs=_estimated_seconds(steps),
            workoutSegments=[segment],
            description=description[:1024] if description else None,
        )
