"""Diagnóstico ÚNICO do agendamento no Garmin (rota não-oficial).

NÃO faz parte do produto — roda UMA vez pra descobrir o que o Garmin
realmente devolve, imprime os retornos crus e LIMPA tudo no fim (cria só 1
treino de teste numa data distante). Depois disso a reconciliação remove
treino sem chute.

Responde 3 perguntas:
  1) qual a chave do schedule_id no retorno de schedule_workout?
  2) qual o formato do calendário (get_scheduled_workouts)?
  3) apagar o treino (delete_workout) já tira do calendário sozinho?
     -> se sim, a remoção fica trivial e sem depender de chute nenhum.

Pré-requisito: login feito uma vez (python garmin_login.py <profile>).

Uso:  python garmin_diagnostico.py <profile>
Ex.:  python garmin_diagnostico.py renato2
"""

import json
import sys
from datetime import date, timedelta

from app.application.garmin.garmin_workout_builder import (
    GarminWorkoutBuilder,
)
from app.domain.entities.planned_session import PlannedSession
from app.infrastructure.integrations.garmin.garmin_client import (
    GarminClient,
)

TITLE_HINT = "DIAGNOSTICO"


def _dump(label: str, value) -> None:

    print(f"\n----- {label} -----")

    try:

        print(json.dumps(value, indent=2, ensure_ascii=False, default=str))

    except TypeError:

        print(repr(value))


def _test_session() -> PlannedSession:

    return PlannedSession(
        day="Monday",
        workout_type="Rodagem",
        objective="diagnostico",
        planned_distance_km=5.0,
        planned_duration_minutes=None,
        target_pace_min="6:00",
        target_pace_max="6:30",
        purpose="RunMind DIAGNOSTICO - pode apagar",
    )


def _find_referring_items(calendar, workout_id) -> list[dict]:
    """Acha, no calendário (formato desconhecido), os dicts que mencionam
    nosso treino — varre recursivamente por workout_id ou pelo título."""

    hits: list[dict] = []

    def walk(node) -> None:

        if isinstance(node, dict):

            blob = json.dumps(node, default=str)

            if str(workout_id) in blob or TITLE_HINT in blob:

                hits.append(node)

            for value in node.values():

                walk(value)

        elif isinstance(node, list):

            for value in node:

                walk(value)

    walk(calendar)

    return hits


def _guess_schedule_id(items: list[dict], workout_id) -> object | None:

    for item in items:

        for key in (
            "workoutScheduleId", "scheduleId", "id", "calendarItemId",
        ):

            value = item.get(key)

            if value and value != workout_id:

                print(f">>> candidato a schedule_id: {key} = {value}")

                return value

    return None


def main(profile: str) -> None:

    garmin = GarminClient.connect(profile)

    on_date = date.today() + timedelta(days=45)

    title = "RunMind DIAGNOSTICO apagar"

    print(f"Data de teste (distante, não colide com plano): {on_date}")

    # 1) sobe o treino de teste pra biblioteca
    workout = GarminWorkoutBuilder.build(
        _test_session(),
        name=title,
        description="RunMind DIAGNOSTICO - pode apagar",
    )

    upload = garmin.upload_running_workout(workout)

    _dump("1) RETORNO DO UPLOAD", upload)

    workout_id = (
        upload.get("workoutId")
        or upload.get("workoutIdStr")
        or (upload.get("workout") or {}).get("workoutId")
    )

    print(f"\n>>> workout_id extraído: {workout_id}")

    if not workout_id:

        print("!!! não achei o workout_id — me cole o retorno acima")

        return

    deleted = False

    schedule_id = None

    try:

        # 2) agenda -> AQUI mora a chave que eu chutei (schedule_id)
        schedule = garmin.schedule_workout(workout_id, on_date.isoformat())

        _dump("2) RETORNO DO SCHEDULE  <-- procuro o schedule_id aqui", schedule)

        # 3) calendário do mês -> formato + onde vive o id do agendamento
        calendar = garmin.get_scheduled_workouts(on_date.year, on_date.month)

        if isinstance(calendar, dict):

            print("\n----- 3) CHAVES DO CALENDÁRIO (topo) -----")

            print(list(calendar.keys()))

        items = _find_referring_items(calendar, workout_id)

        _dump("3b) ITENS DO CALENDÁRIO que referenciam nosso treino", items)

        schedule_id = _guess_schedule_id(items, workout_id)

        # 4) PERGUNTA-CHAVE: delete_workout sozinho tira do calendário?
        print("\n===== CASCATE: delete_workout tira do calendário? =====")

        garmin.delete_workout(workout_id)

        deleted = True

        after = garmin.get_scheduled_workouts(on_date.year, on_date.month)

        still_there = _find_referring_items(after, workout_id)

        if not still_there:

            print(
                "✅ CASCATEIA: delete_workout(workout_id) já removeu do "
                "calendário. A remoção fica trivial — sem schedule_id!"
            )

        else:

            print(
                "❌ NÃO cascateia: o agendamento CONTINUA no calendário. "
                "Precisamos de unschedule com o schedule_id."
            )

            if schedule_id:

                garmin.unschedule_workout(schedule_id)

                confirm = garmin.get_scheduled_workouts(
                    on_date.year, on_date.month,
                )

                gone = not _find_referring_items(confirm, workout_id)

                print(
                    f"   -> unschedule_workout({schedule_id}) limpou? "
                    f"{'✅ sim' if gone else '❌ não'}"
                )

            else:

                print(
                    "   !!! não identifiquei o schedule_id nos itens — me "
                    "cole a saída 3b que eu acho a chave certa"
                )

    finally:

        # rede de segurança: garante que o treino de teste some
        if not deleted:

            try:

                garmin.delete_workout(workout_id)

            except Exception as e:

                print(f"(limpeza) falha ao apagar o treino de teste: {e}")

    print(
        "\nDiagnóstico concluído. Se sobrar algo, é só o treino de teste "
        "numa data distante — dá pra apagar no app sem medo."
    )


if __name__ == "__main__":

    if len(sys.argv) < 2:

        print("Uso: python garmin_diagnostico.py <profile>")

        sys.exit(1)

    main(sys.argv[1])
