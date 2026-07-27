"""Empurra pro Garmin APENAS o treino avulso (origin='oneoff') de um dia —
sem tocar no resto do plano nem passar pelo reconciliador da semana. É o que
o 'quer no relógio? SIM' do treino avulso chama, inclusive pra atleta de
treinador externo (o avulso é NOSSO, não do treinador)."""

from datetime import date

from app.application.garmin.garmin_push import push_session
from app.application.planner.current_plan_provider import CurrentPlanProvider
from app.core.weekdays import WEEKDAYS
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


async def push_one_off(profile: str, on_date: date) -> dict:
    """Sobe a sessão avulsa daquele dia. Retorna {ok, workout, date} ou
    {ok: False, error}."""

    _, plan = await CurrentPlanProvider.for_profile(profile)

    target_day = WEEKDAYS[on_date.weekday()]

    session = next(
        (
            s
            for s in plan.sessions
            if s.day == target_day and getattr(s, "origin", "plan") == "oneoff"
        ),
        None,
    )

    if session is None:

        return {"ok": False, "error": "treino avulso não encontrado no dia"}

    if not GarminClient.is_connected(profile):

        return {"ok": False, "error": "garmin desconectado"}

    garmin = GarminClient.connect(profile)

    outcome = push_session(profile, session, on_date, garmin)

    if outcome.get("ok"):

        # guarda o registro do push na sessão (idempotência de re-push)
        session.garmin = {
            "workout_id": outcome.get("workout_id"),
            "schedule_id": outcome.get("schedule_id"),
            "date": outcome.get("date"),
        }

        WeeklyPlanRepository().save(profile, plan)

    return {
        **outcome,
        "workout": session.workout_type,
        "date": on_date.isoformat(),
    }
