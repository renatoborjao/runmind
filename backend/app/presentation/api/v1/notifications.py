from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.infrastructure.persistence.app_notification_repository import (
    AppNotificationRepository,
)
from app.infrastructure.persistence.push_subscription_repository import (
    PushSubscriptionRepository,
)
from app.presentation.api.deps import current_profile

router = APIRouter(tags=["Notifications"])


# ==========================
# CENTRAL DE NOTIFICAÇÕES (sino/feed no app)
# ==========================


@router.get("/notifications")
async def list_notifications(profile: str = Depends(current_profile)):
    """Feed de notificações do atleta (mais novas primeiro) + contagem de
    não-lidas pro badge do sino."""

    repo = AppNotificationRepository()

    items = repo.load(profile)

    unread = sum(1 for i in items if not i.get("read"))

    return {"items": items, "unread": unread}


class MarkReadIn(BaseModel):

    # ids específicas; ausente/None = marca TODAS como lidas
    ids: list[str] | None = None


@router.post("/notifications/read")
async def mark_notifications_read(
    body: MarkReadIn, profile: str = Depends(current_profile)
):
    """Marca notificações como lidas (todas, ou as `ids` informadas)."""

    repo = AppNotificationRepository()

    repo.mark_read(profile, body.ids)

    return {"unread": repo.unread_count(profile)}


# ==========================
# WEB PUSH (inscrição do navegador)
# ==========================


@router.get("/push/public-key")
async def push_public_key():
    """Chave pública VAPID (application server key) pro navegador se inscrever.
    Não é segredo. Vazia = push desligado no servidor."""

    return {"key": get_settings().vapid_public_key or ""}


class PushSubscribeIn(BaseModel):

    endpoint: str
    keys: dict | None = None


@router.post("/push/subscribe")
async def push_subscribe(
    body: PushSubscribeIn, profile: str = Depends(current_profile)
):
    """Registra a inscrição de push deste navegador/aparelho pro atleta logado."""

    if not body.endpoint:

        raise HTTPException(status_code=422, detail="Inscrição inválida.")

    PushSubscriptionRepository().add(
        profile,
        {"endpoint": body.endpoint, "keys": body.keys or {}},
    )

    return {"ok": True}


class PushUnsubscribeIn(BaseModel):

    endpoint: str


@router.post("/push/unsubscribe")
async def push_unsubscribe(
    body: PushUnsubscribeIn, profile: str = Depends(current_profile)
):
    """Remove a inscrição deste aparelho (o atleta desligou as notificações)."""

    PushSubscriptionRepository().remove(profile, body.endpoint)

    return {"ok": True}
