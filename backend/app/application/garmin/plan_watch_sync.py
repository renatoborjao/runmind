"""Mantém o Garmin em sincronia depois que o plano da semana é REGERADO
(entrega de domingo) — re-empurra a semana inteira pro relógio.

Guarda de ouro: só ressincroniza quem JÁ tinha o plano no relógio (tem
snapshot em `PushedPlanStore`). Quem nunca sincronizou NÃO é surpreendido com
treinos aparecendo no relógio do nada — pra esse, o push segue opt-in
('manda pro relógio').

FULL REFRESH: apaga a semana e recria tudo, pra TODOS os treinos caírem na aba
'Programado'. O incremental (reconciliar só o que mudou) deixava os treinos
NOVOS em 'Meus treinos' e só os inalterados em 'Programado' — o split que o
Renato viu no FR165. Reusa o MESMO caminho do domingo/mudança-de-dia
(`push_current_plan`). Ver [[project_rede_relogio]]."""

from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.persistence.pushed_plan_store import PushedPlanStore


async def resync_watch_if_pushed(profile: str, plan: TrainingPlan) -> bool:
    """Re-empurra a semana pro relógio com FULL REFRESH (tudo em 'Programado').
    Devolve True se sincronizou, False se não havia o que sincronizar
    (desconectado ou nunca empurrou). Best-effort: qualquer falha aqui NUNCA
    derruba a resposta ao atleta (o relógio reconcilia na próxima; a fonte de
    verdade é o plano no app). O `plan` já foi salvo pelo chamador — o
    `push_current_plan` relê o mesmo do repositório."""

    try:

        if not GarminClient.is_connected(profile):

            return False

        # nunca empurrou pro relógio: não surpreende com treinos do nada
        if PushedPlanStore.load(profile) is None:

            return False

        # full refresh: apaga os templates futuros e recria+reagenda a semana
        # inteira -> repovoa 'Programado' com TODOS os treinos (o incremental
        # deixava os novos em 'Meus treinos'). Import tardio evita ciclo.
        from app.application.garmin.push_current_plan import push_current_plan

        await push_current_plan(profile, full_refresh=True)

        return True

    except Exception as e:

        print(f"Falha ao ressincronizar o relógio de '{profile}': {e}")

        return False
