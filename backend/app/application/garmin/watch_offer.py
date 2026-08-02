"""Oferta de atualizar o relógio depois de uma mudança MID-WEEK no plano
(mover treino, trocar o dia do longão). Em vez de empurrar automático, o coach
PERGUNTA — e o 'sim' seguinte empurra pelo caminho opt-in que já existe
(`GarminSync.handle_reply` → `push_current_plan`).

Domingo (semana nova) segue AUTOMÁTICO — lá o atleta já optou pelo sync
semanal; aqui é uma mudança pontual, então pede confirmação."""

from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.integrations.garmin.garmin_offer_store import (
    GarminOfferStore,
)
from app.infrastructure.persistence.pushed_plan_store import PushedPlanStore

_OFFER_LINE = (
    "\n\n⌚ Quer que eu atualize esses treinos no seu relógio também? "
    "Responde *sim*."
)


def watch_update_offer(profile: str) -> str:
    """Linha de oferta pra atualizar o relógio + arma o pending pro 'sim'.
    SÓ pra quem tem Garmin conectado E já sincronizou antes (o relógio dele
    ficou desatualizado com a mudança) — pra quem nunca sincronizou, nada
    (sem ruído; ele opta no domingo). String vazia quando não se aplica."""

    if not GarminClient.is_connected(profile):

        return ""

    # nunca empurrou: não é hora de oferecer no meio de uma mudança pontual
    if PushedPlanStore.load(profile) is None:

        return ""

    GarminOfferStore.set_pending(profile)

    return _OFFER_LINE
