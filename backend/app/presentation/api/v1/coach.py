from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.application.events.coach_conversation import CoachConversationEvent
from app.application.notifications.app_inbox import deep_link_for
from app.infrastructure.persistence.app_notification_repository import (
    AppNotificationRepository,
)
from app.infrastructure.persistence.conversation_repository import (
    ConversationRepository,
)
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/coach", tags=["Coach"])


class MessageIn(BaseModel):

    text: str


def _at(value: str | None) -> datetime:
    """Parseia o timestamp (ISO com fuso) pra ordenar; naive/nulo cai no início."""

    try:

        return datetime.fromisoformat(value)

    except (TypeError, ValueError):

        return datetime.min.replace(tzinfo=UTC)


@router.get("/messages")
async def history(profile: str = Depends(current_profile)):
    """Timeline COMPLETA do coach — igual ao Telegram: a conversa (o que o atleta
    pergunta e o coach responde) MAIS os toques PROATIVOS (análise do treino,
    lembrete do dia, alertas), mesclados em ordem. Cada proativo vem com `kind`,
    `title` e `url` (atalho: tocar abre a tela certa — treino do dia, atividade…).
    A central de notificações vira só a campainha; o conteúdo mora aqui."""

    turns = ConversationRepository().recent_turns(profile, limit=40)

    pushes = AppNotificationRepository().load(profile)

    items: list[dict] = []

    for t in turns:

        items.append(
            {
                "role": t.get("role"),
                "text": t.get("text"),
                "at": t.get("timestamp"),
                "kind": None,
                "title": None,
                "url": None,
            }
        )

    for n in pushes:

        items.append(
            {
                "role": "coach",
                "text": n.get("text"),
                "at": n.get("created_at"),
                "kind": n.get("kind"),
                "title": n.get("title"),
                "url": deep_link_for(n.get("kind")),
            }
        )

    items.sort(key=lambda it: _at(it.get("at")))

    return {"messages": items[-60:]}


@router.post("/messages")
async def send(body: MessageIn, profile: str = Depends(current_profile)):
    """Manda uma mensagem pro coach e devolve a resposta — MESMO pipeline do
    Telegram (decide/executa/aprende), mas sem reenviar pelo canal (notify=False)."""

    text = (body.text or "").strip()

    if not text:

        raise HTTPException(status_code=400, detail="mensagem vazia")

    try:

        reply = await CoachConversationEvent.execute(
            profile=profile,
            incoming_text=text,
            notify=False,
        )

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))

    return {"reply": reply}
