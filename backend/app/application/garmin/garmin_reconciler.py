"""Reconcilia o plano da semana com o calendário do Garmin do atleta.

O plano é a FONTE DE VERDADE; o relógio é uma PROJEÇÃO dele. Quando o plano
muda no meio da semana (aversão, treino movido, dia pulado, furou-ontem), a
reconciliação aplica só o MÍNIMO no Garmin — sem duplicar nem deixar treino-
fantasma:

- sessão nova (dia que não tinha nada)           -> empurra
- mesma sessão, mesmo conteúdo e data            -> não faz nada (idempotente)
- sessão mudou de conteúdo ou de dia             -> desagenda a antiga + empurra
- sessão sumiu do plano (drop) ou virou passado  -> desagenda a antiga

Só mexe em treino de HOJE em diante: o que já passou fica como está.
"""

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date

from app.application.garmin.garmin_push import push_session, remove_session
from app.core.clock import today_local
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan

_RUNNING_KINDS = {"run", "walk", "run_walk"}


def session_fingerprint(session: PlannedSession) -> str:
    """Hash curto do que DEFINE o treino no relógio (modalidade, tipo,
    distância, paces e passos). Se qualquer um muda, o fingerprint muda e a
    reconciliação sabe que precisa re-empurrar. Texto de objetivo/estrutura
    não entra — mudar só a descrição não justifica refazer o treino."""

    payload = {
        "kind": session.kind,
        "workout_type": session.workout_type,
        "distance_km": session.planned_distance_km,
        "pace_min": session.target_pace_min,
        "pace_max": session.target_pace_max,
        "steps": [
            asdict(step) if is_dataclass(step) else step
            for step in (session.steps or [])
        ],
    }

    blob = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )

    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


class GarminReconciler:

    @staticmethod
    def reconcile(
        profile: str,
        previous_plan: TrainingPlan | None,
        current_plan: TrainingPlan,
        reference_date: date | None = None,
        garmin=None,
    ) -> list[dict]:
        """Aplica no Garmin a diferença entre o plano anterior e o atual.
        Grava o registro de push em cada sessão de `current_plan` (o chamador
        persiste o plano depois). Retorna um resultado por ação. `garmin` já
        conectado (do chamador) é reusado em todas as ops — um login só."""

        reference_date = reference_date or today_local()

        prev_by_day = {
            session.day.lower(): session
            for session in (previous_plan.sessions if previous_plan else [])
            if session.kind in _RUNNING_KINDS
        }

        results: list[dict] = []

        current_days: set[str] = set()

        for session in current_plan.sessions:

            if session.kind not in _RUNNING_KINDS:

                continue

            day = session.day.lower()

            current_days.add(day)

            on_date = current_plan.session_date(session)

            # não mexe no passado: o que já era pra ter acontecido fica
            if on_date < reference_date:

                continue

            results.append(
                GarminReconciler._sync_session(
                    profile,
                    session,
                    on_date,
                    prev_by_day.get(day),
                    garmin,
                )
            )

        results.extend(
            GarminReconciler._remove_dropped(
                profile,
                prev_by_day,
                current_days,
                reference_date,
                garmin,
            )
        )

        return results

    @staticmethod
    def _sync_session(
        profile: str,
        session: PlannedSession,
        on_date: date,
        previous: PlannedSession | None,
        garmin=None,
    ) -> dict:

        fingerprint = session_fingerprint(session)

        # registro do que já foi pro relógio: do plano anterior (regeração)
        # ou da própria sessão (re-push do mesmo plano)
        record = (previous.garmin if previous else None) or session.garmin

        unchanged = (
            record is not None
            and record.get("fingerprint") == fingerprint
            and record.get("date") == on_date.isoformat()
        )

        base = {
            "day": session.day,
            "date": on_date.isoformat(),
            "workout": session.workout_type,
        }

        # já está no relógio, igualzinho: não toca (idempotente)
        if unchanged:

            session.garmin = record

            return {**base, "ok": True, "action": "kept"}

        # empurra o NOVO primeiro; só remove o antigo depois que o novo
        # entrou. Push que falha não pode deixar o atleta sem treino no dia
        # — mantém o estado anterior intacto pra reconciliar de novo depois.
        try:

            outcome = push_session(profile, session, on_date, garmin)

        except Exception as e:

            session.garmin = record

            return {**base, "ok": False, "action": "failed", "error": str(e)}

        if not outcome.get("ok"):

            session.garmin = record

            return {**base, **outcome, "action": "failed"}

        # novo garantido no relógio: agora tira o antigo (se havia)
        if record:

            try:

                remove_session(profile, record, garmin)

            except Exception as e:

                print(f"Falha ao remover treino antigo ({session.day}): {e}")

        session.garmin = {
            "workout_id": outcome["workout_id"],
            "schedule_id": outcome.get("schedule_id"),
            "date": on_date.isoformat(),
            "fingerprint": fingerprint,
        }

        return {
            **base,
            "ok": True,
            "action": "replaced" if record else "pushed",
            "workout_id": outcome["workout_id"],
        }

    @staticmethod
    def _remove_dropped(
        profile: str,
        prev_by_day: dict[str, PlannedSession],
        current_days: set[str],
        reference_date: date,
        garmin=None,
    ) -> list[dict]:
        """Dias que tinham treino no plano anterior e sumiram do atual
        (drop, virou descanso, ou moveu pra outro dia): desagenda o que
        ficou órfão no relógio — mas só no futuro."""

        results: list[dict] = []

        for day, previous in prev_by_day.items():

            if day in current_days:

                continue

            record = previous.garmin

            if not record:

                continue

            when = record.get("date")

            if when and date.fromisoformat(when) < reference_date:

                continue

            try:

                remove_session(profile, record, garmin)

                results.append(
                    {"day": previous.day, "ok": True, "action": "removed"}
                )

            except Exception as e:

                results.append(
                    {
                        "day": previous.day,
                        "ok": False,
                        "action": "remove_failed",
                        "error": str(e),
                    }
                )

        return results
