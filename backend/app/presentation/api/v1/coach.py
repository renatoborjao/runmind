from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.application.events.coach_conversation import CoachConversationEvent
from app.infrastructure.persistence.conversation_repository import (
    ConversationRepository,
)
from app.presentation.api.deps import current_profile

router = APIRouter(prefix="/coach", tags=["Coach"])


class MessageIn(BaseModel):

    text: str


@router.get("/messages")
async def history(profile: str = Depends(current_profile)):
    """Histórico da conversa do atleta logado (mesma conversa do Telegram)."""

    turns = ConversationRepository().recent_turns(profile, limit=40)

    return {
        "messages": [
            {"role": t.get("role"), "text": t.get("text"), "at": t.get("timestamp")}
            for t in turns
        ]
    }


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
