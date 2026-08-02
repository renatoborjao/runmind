"""Mantém o Garmin em sincronia depois que o plano da semana é REGERADO
(preferência de rotina, troca de objetivo) — o mesmo que o mover/pular já faz,
mas pro caminho da regeração inteira da semana.

Guarda de ouro: só ressincroniza quem JÁ tinha o plano no relógio (tem
snapshot em `PushedPlanStore`). Quem nunca sincronizou NÃO é surpreendido com
treinos aparecendo no relógio do nada — pra esse, o push segue opt-in
('manda pro relógio')."""

from app.application.garmin.garmin_reconciler import GarminReconciler
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.persistence.pushed_plan_store import PushedPlanStore
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)


async def resync_watch_if_pushed(profile: str, plan: TrainingPlan) -> bool:
    """Reconcilia o plano REGERADO contra o último snapshot empurrado, pra o
    relógio refletir a mudança (remove os treinos antigos nossos, empurra os
    novos — sem duplicar). Devolve True se sincronizou, False se não havia o
    que sincronizar (desconectado ou nunca empurrou). Best-effort: qualquer
    falha aqui NUNCA derruba a resposta ao atleta (o relógio reconcilia na
    próxima; a fonte de verdade é o plano no app)."""

    try:

        if not GarminClient.is_connected(profile):

            return False

        # nunca empurrou pro relógio: não surpreende com treinos do nada
        previous = PushedPlanStore.load(profile)

        if previous is None:

            return False

        # conecta uma vez e reusa; reconcilia o novo contra o que estava lá
        garmin = GarminClient.connect(profile)

        GarminReconciler.reconcile(
            profile,
            previous_plan=previous,
            current_plan=plan,
            garmin=garmin,
        )

        # persiste os registros de push gravados nas sessões + novo snapshot
        WeeklyPlanRepository().save(profile, plan)

        PushedPlanStore.save(profile, plan)

        return True

    except Exception as e:

        print(f"Falha ao ressincronizar o relógio de '{profile}': {e}")

        return False
