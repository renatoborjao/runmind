import copy

from app.domain.entities.plan_proposal import PlanProposal
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.domain.entities.workout_step import parse_steps
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


class PlanChangeApplier:
    """Efetiva no plano vivo a mudança que o atleta ACEITOU e reconcilia o
    relógio (só o que mudou; nada de duplicata). É o passo 'aplica no sim' —
    a produção do candidato acontece antes, na proposta."""

    @staticmethod
    def apply(
        profile: str,
        proposal: PlanProposal,
    ) -> TrainingPlan | None:
        """Aplica as operações da proposta. Devolve o plano atualizado, ou
        None se a proposta ficou obsoleta (semana virou / sem plano)."""

        repository = WeeklyPlanRepository()

        live = repository.load(profile)

        # semana virou ou sumiu o plano: proposta obsoleta, não aplica
        if live is None or live.week_start.isoformat() != proposal.week_start:

            return None

        updated = copy.deepcopy(live)

        PlanChangeApplier._apply_operations(updated, proposal.operations)

        # NÃO empurra pro relógio aqui: mudança mid-week PERGUNTA antes (o
        # ProposalFlow oferece "quer no relógio?" e o 'sim' sincroniza pelo
        # caminho opt-in). Só o plano do domingo vai automático pro Garmin.
        repository.save(profile, updated)

        return updated

    @staticmethod
    def _apply_operations(
        plan: TrainingPlan,
        operations: list[dict],
    ) -> None:

        for op in operations:

            action = op.get("action")

            day = (op.get("day") or "").lower()

            if not day:

                continue

            # tira o que houver no dia (replace e drop começam limpando)
            plan.sessions = [
                session
                for session in plan.sessions
                if session.day.lower() != day
            ]

            if action == "replace":

                plan.sessions.append(
                    PlanChangeApplier._session_from_dict(op["session"])
                )

        PlanChangeApplier._recompute(plan)

    @staticmethod
    def _session_from_dict(data: dict) -> PlannedSession:

        data = dict(data)

        # passos voltam como WorkoutStep (fonte de verdade pro push guiado)
        if "steps" in data:

            data["steps"] = parse_steps(data["steps"])

        # candidato nasce sem registro de Garmin — a reconciliação o cria
        data.pop("garmin", None)

        return PlannedSession(**data)

    @staticmethod
    def _recompute(plan: TrainingPlan) -> None:
        """Mantém os agregados coerentes e as sessões em ordem de semana."""

        plan.sessions.sort(key=lambda session: plan.session_date(session))

        plan.running_days = [
            session.day
            for session in plan.sessions
            if session.kind == "run"
        ]

        plan.weekly_volume = round(
            sum(
                session.planned_distance_km or 0
                for session in plan.sessions
            ),
            1,
        )
