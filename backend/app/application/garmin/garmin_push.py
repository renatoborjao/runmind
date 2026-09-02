"""Empurra sessões do plano pro calendário do Garmin do atleta: monta o
treino estruturado, sobe pro Garmin Connect e agenda na data — aí sincroniza
pro relógio sozinho. Não-oficial (garminconnect); falha de uma sessão não
derruba as outras."""

from datetime import date

from app.application.coach.writer.labels import plan_session_title
from app.application.garmin.garmin_workout_builder import (
    GarminWorkoutBuilder,
)
from app.domain.entities.planned_session import PlannedSession
from app.infrastructure.integrations.garmin.garmin_client import (
    GarminClient,
)


def _workout_name(session: PlannedSession) -> str:

    # fonte ÚNICA do título (mesmo nome no relógio E no Strava, sem drift)
    return plan_session_title(session)


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


# prefixos dos treinos que NÓS criamos no Garmin (marca atual + a antiga, do
# rebrand RunMind→Ritmind) — a varredura só mexe no que é nosso, nunca no que o
# atleta criou por conta, nem no histórico de atividades.
OUR_WORKOUT_PREFIXES = ("Ritmind ·", "RunMind ·")


def sweep_orphan_workouts(
    profile: str,
    keep_ids: set,
    garmin=None,
) -> list:
    """Apaga da BIBLIOTECA do Garmin os treinos NOSSOS que não estão no plano
    atual (`keep_ids`) — evita o acúmulo de órfãos de semanas/rebrand passados
    quando a reconciliação por snapshot perde o elo. Seguro: só toca em treinos
    com o nosso prefixo (não nos do atleta) e NUNCA no histórico de atividades
    (delete_workout só apaga o template/agendamento). Os avulsos ficam — vivem
    dentro da semana, logo estão no plano e em keep_ids. Best-effort: falhar
    aqui nunca derruba o push."""

    garmin = garmin or GarminClient.connect(profile)

    # workouts PROTEGIDOS (prova/avulso empurrado fora do plano) nunca são
    # varridos — senão o push de domingo apagaria o treino de prova futuro.
    from app.infrastructure.persistence.protected_workout_store import (
        ProtectedWorkoutStore,
    )

    keep = set(keep_ids) | ProtectedWorkoutStore().ids(profile)

    removed = []

    try:

        for workout in garmin.get_workouts(0, 100):

            workout_id = workout.get("workoutId")

            name = workout.get("workoutName") or ""

            if workout_id in keep or not name.startswith(OUR_WORKOUT_PREFIXES):

                continue

            try:

                garmin.delete_workout(workout_id)

                removed.append(workout_id)

            except Exception as e:  # noqa: BLE001 — varredura best-effort

                print(f"Sweep: falha ao apagar {workout_id} ({name}): {e}")

    except Exception as e:  # noqa: BLE001 — varredura best-effort

        print(f"Sweep de órfãos falhou p/ '{profile}': {e}")

    return removed


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
