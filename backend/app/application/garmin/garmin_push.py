"""Empurra sessões do plano pro calendário do Garmin do atleta: monta o
treino estruturado, sobe pro Garmin Connect e agenda na data — aí sincroniza
pro relógio sozinho. Não-oficial (garminconnect); falha de uma sessão não
derruba as outras."""

from datetime import date

from app.application.coach.writer.labels import plan_workout_label
from app.application.garmin.garmin_workout_builder import (
    GarminWorkoutBuilder,
)
from app.domain.entities.planned_session import PlannedSession
from app.infrastructure.integrations.garmin.garmin_client import (
    GarminClient,
)


def _workout_name(session: PlannedSession) -> str:

    # rótulo amigável (LONG_RUN -> Longão), nunca o código cru
    label = plan_workout_label(
        session.workout_type,
        session.planned_distance_km,
    )

    if session.planned_distance_km:

        return f"RunMind · {label} {session.planned_distance_km:.1f}km"

    return f"RunMind · {label}"


def _description(session: PlannedSession) -> str:
    """Plano detalhado (passos da IA) vai na descrição do treino — o atleta
    vê no app/relógio, especialmente útil nos tiros (que a v1 não estrutura
    passo a passo ainda)."""

    parts = []

    if session.purpose:

        parts.append(f"Objetivo: {session.purpose}")

    if session.structure:

        parts.append(session.structure)

    return "\n".join(parts)


def push_session(
    profile: str,
    session: PlannedSession,
    on_date: date,
    garmin=None,
) -> dict:
    """Sobe e agenda UMA sessão. Retorna {ok, workout_id, date} ou
    {ok: False, error}. `garmin` já conectado é reusado (a reconciliação
    conecta uma vez e reusa em todas as sessões, em vez de logar por op)."""

    garmin = garmin or GarminClient.connect(profile)

    workout = GarminWorkoutBuilder.build(
        session,
        name=_workout_name(session),
        description=_description(session),
    )

    if session.kind == "walk":

        result = garmin.upload_walking_workout(workout)

    else:

        result = garmin.upload_running_workout(workout)

    workout_id = (
        result.get("workoutId")
        or result.get("workoutIdStr")
        or (result.get("workout") or {}).get("workoutId")
    )

    if not workout_id:

        return {"ok": False, "error": f"sem workoutId no retorno: {result}"}

    date_str = on_date.isoformat()

    schedule = garmin.schedule_workout(workout_id, date_str)

    return {
        "ok": True,
        "workout_id": workout_id,
        "schedule_id": _schedule_id(schedule),
        "date": date_str,
    }


def _schedule_id(schedule) -> int | str | None:
    """O id do AGENDAMENTO (não do treino) que o `schedule_workout`
    devolve — é ele que o `unschedule_workout` usa pra tirar do calendário
    sem apagar o template."""

    if not isinstance(schedule, dict):

        return None

    return schedule.get("workoutScheduleId") or schedule.get("scheduleId")


def remove_session(profile: str, record: dict, garmin=None) -> dict:
    """Tira do Garmin o treino que uma sessão colocou lá. Confirmado no
    device (perfil renato2, jul/2026): apagar o template com delete_workout
    JÁ REMOVE o agendamento do calendário junto (cascateia) — não precisa
    desagendar, então basta o workout_id (que vem confiável do upload).
    `garmin` já conectado é reusado (evita novo login por remoção)."""

    garmin = garmin or GarminClient.connect(profile)

    workout_id = record.get("workout_id")

    if workout_id:

        garmin.delete_workout(workout_id)

    return {"ok": True, "workout_id": workout_id}


def push_week(
    profile: str,
    sessions_with_dates: list[tuple[PlannedSession, date]],
) -> list[dict]:
    """Empurra a semana inteira. Cada sessão é independente: se uma falha,
    loga e segue pras outras."""

    results = []

    for session, on_date in sessions_with_dates:

        try:

            outcome = push_session(profile, session, on_date)

        except Exception as e:

            outcome = {"ok": False, "error": str(e), "day": session.day}

            print(f"Falha ao empurrar {session.day} pro Garmin: {e}")

        results.append(outcome)

    return results
