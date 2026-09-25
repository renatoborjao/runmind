from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.application.coach.media.coach_media_message import CoachMediaMessage
from app.application.events.coach_conversation import CoachConversationEvent
from app.application.notifications.app_inbox import deep_link_for
from app.infrastructure.persistence.chat_media_store import (
    ChatMediaStore,
    decode_data_url,
)
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


class PhotoIn(BaseModel):

    data: str               # data URL da imagem (o app já reduz/converte p/ JPEG)
    caption: str = ""


class VoiceIn(BaseModel):

    data: str               # data URL do áudio gravado (webm/opus ou mp4/aac)
    duration: float | None = None


# tetos do que chega decodificado (o app já comprime; isso é só guarda)
_MAX_PHOTO_BYTES = 12 * 1024 * 1024

_MAX_VOICE_BYTES = 15 * 1024 * 1024

_PHOTO_TYPES = ("image/", "application/pdf")


def _media_url(turn: dict) -> str | None:
    """URL da foto do turno (servida só pro próprio atleta)."""

    att = turn.get("attachment") or {}

    if att.get("type") == "image" and att.get("id"):

        return f"/api/v1/coach/media/{att['id']}"

    return None


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

        # turno de mídia: o balão mostra a legenda/transcrição + a foto (o
        # "text" cru é o que o coach leu — descrição da imagem etc.)
        shown = t.get("display_text")

        items.append(
            {
                "role": t.get("role"),
                "text": shown if shown is not None else t.get("text"),
                "at": t.get("timestamp"),
                "kind": None,
                "title": None,
                "url": None,
                "image_url": _media_url(t),
            }
        )

    for n in pushes:

        # social (seguir/kudos/pedidos) vive só na central/comunidade, não na
        # timeline do coach — aqui é conversa de treino
        if str(n.get("kind") or "").startswith("social_"):

            continue

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


@router.post("/photo")
async def send_photo(body: PhotoIn, profile: str = Depends(current_profile)):
    """Foto (ou PDF) pro coach: ele VÊ a imagem e responde pelo mesmo pipeline
    da conversa; com treinador externo, planilha vira plano. Ver
    CoachMediaMessage."""

    try:

        raw, mimetype = decode_data_url(body.data)

    except ValueError:

        raise HTTPException(status_code=400, detail="imagem inválida")

    if len(raw) > _MAX_PHOTO_BYTES:

        raise HTTPException(status_code=413, detail="imagem grande demais")

    if mimetype and not mimetype.startswith(_PHOTO_TYPES):

        raise HTTPException(status_code=415, detail="formato não suportado")

    try:

        reply = await CoachMediaMessage.image(
            profile,
            raw,
            mimetype or "image/jpeg",
            caption=body.caption,
            notify=False,
        )

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))

    return {"reply": reply}


@router.post("/voice")
async def send_voice(body: VoiceIn, profile: str = Depends(current_profile)):
    """Áudio pro coach: transcreve (whisper local) e segue como mensagem. Devolve
    a transcrição (o app mostra no balão) e a resposta."""

    try:

        raw, _mimetype = decode_data_url(body.data)

    except ValueError:

        raise HTTPException(status_code=400, detail="áudio inválido")

    if len(raw) > _MAX_VOICE_BYTES:

        raise HTTPException(status_code=413, detail="áudio grande demais")

    try:

        return await CoachMediaMessage.voice(
            profile, raw, duration_seconds=body.duration, notify=False,
        )

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))


@router.get("/media/{media_id}")
async def media(media_id: str, profile: str = Depends(current_profile)):
    """Foto que o atleta mandou no chat — só o dono vê (a pasta é do perfil
    logado; id validado)."""

    path = ChatMediaStore().path(profile, media_id)

    if path is None:

        raise HTTPException(status_code=404, detail="não encontrada")

    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )
