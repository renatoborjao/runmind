from fastapi import APIRouter
from fastapi import Header
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request

from app.core.config import get_settings

from app.application.events.coach_conversation import (
    CoachConversationEvent,
)
from app.application.events.external_plan_received import (
    ExternalPlanEvent,
)
from app.application.events.onboarding_conversation import (
    OnboardingEvent,
)
from app.application.notifications.notification_service import (
    NotificationService,
)
from app.application.events.training_completed import (
    TrainingCompletedEvent,
)
from app.application.use_cases.owner_resolver import (
    OwnerResolver,
)
from app.domain.value_objects.sports import (
    is_foot_sport,
)
from app.infrastructure.integrations.evolution.inbound_parser import (
    WhatsAppInboundParser,
)
from app.infrastructure.integrations.evolution.phone_normalizer import (
    PhoneNormalizer,
)
from app.infrastructure.integrations.strava.client import (
    StravaClient,
)
from app.infrastructure.integrations.telegram.telegram_inbound_parser import (
    TelegramInboundParser,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)

router = APIRouter(
    prefix="/webhooks",
    tags=["Webhooks"],
)


# ==========================================================
# STRAVA VERIFICATION
# ==========================================================

@router.get("/strava")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):

    if hub_mode != "subscribe":

        raise HTTPException(
            status_code=400,
            detail="Invalid hub.mode",
        )

    if hub_verify_token != "runmind123":

        raise HTTPException(
            status_code=403,
            detail="Invalid verify token",
        )

    return {

        "hub.challenge": hub_challenge

    }


# ==========================================================
# STRAVA EVENTS
# ==========================================================

@router.post("/strava")
async def receive_webhook(
    request: Request,
):

    payload = await request.json()

    print()
    print("=" * 70)
    print("WEBHOOK RECEBIDO")
    print("=" * 70)
    print(payload)
    print("=" * 70)

    # Ignora eventos que não são de atividade
    if payload.get("object_type") != "activity":

        return {

            "ignored": True,

            "reason": "object_type != activity"

        }

    owner_id = payload["owner_id"]

    activity_id = payload["object_id"]

    profile = OwnerResolver.resolve(
        owner_id,
    )

    client = StravaClient(
        profile,
    )

    activity = await client.get_activity(
        activity_id,
    )

    # pedalada/natação/musculação não geram feedback de corrida
    if not is_foot_sport(activity.sport):

        return {

            "ignored": True,

            "reason": f"sport não suportado: {activity.sport}",

        }

    await TrainingCompletedEvent.execute(

        profile=profile,

        activity=activity,

    )

    return {

        "success": True,

        "profile": profile,

        "activity_id": activity_id,

    }


# ==========================================================
# TEST
# ==========================================================

@router.post("/strava/test/{profile}")
async def test_pipeline(
    profile: str,
):

    try:

        result = await TrainingCompletedEvent.execute(
            profile=profile,
        )

        return {

            "status": "success",

            "runner": result["runner"].name,

            "message": result["message"],

        }

    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e),

        )


# ==========================================================
# WHATSAPP INBOUND (Evolution API)
# ==========================================================

@router.post("/whatsapp")
async def receive_whatsapp_webhook(
    request: Request,
):

    payload = await request.json()

    print()
    print("=" * 70)
    print("WHATSAPP WEBHOOK RECEBIDO")
    print("=" * 70)
    print(payload)
    print("=" * 70)

    if payload.get("event") != "messages.upsert":

        return {

            "ignored": True,

            "reason": "event != messages.upsert",

        }

    data = payload.get("data", {})

    if data.get("key", {}).get("fromMe"):

        return {

            "ignored": True,

            "reason": "fromMe == true",

        }

    raw_phone = data.get("key", {}).get("remoteJid", "")

    if WhatsAppInboundParser.is_group_message(raw_phone):

        return {

            "ignored": True,

            "reason": "group or broadcast message",

        }

    text = WhatsAppInboundParser.extract_text(data)

    media = WhatsAppInboundParser.extract_media(data)

    if not text and not media:

        return {

            "ignored": True,

            "reason": "no supported content found",

        }

    phone = PhoneNormalizer.normalize(raw_phone)

    # Falha aqui dentro NUNCA pode virar 500: a Evolution reenvia o
    # webhook em erro, reprocessando a mesma mensagem várias vezes
    # (tempestade de retry + chamadas duplicadas ao Gemini).
    try:

        return await route_inbound(
            channel="whatsapp",
            address=phone,
            text=text,
            media=media,
            sender_name=data.get("pushName", ""),
        )

    except Exception as e:

        print(f"Falha ao processar mensagem de {phone}: {e}")

        return {

            "success": False,

            "error": str(e),

        }


async def route_inbound(
    channel: str,
    address: str,
    text: str | None,
    media: dict | None,
    sender_name: str,
) -> dict:
    """Roteamento agnóstico ao canal (WhatsApp/Telegram): resolve o
    atleta pelo endereço e despacha onboarding, plano externo ou
    conversa."""

    repo = RunnerProfileRepository()

    if channel == "telegram":

        profile = repo.find_by_telegram_id(address)

    else:

        profile = repo.find_by_phone(address)

    # endereço desconhecido: inicia (ou continua) o cadastro
    if profile is None:

        reply = await OnboardingEvent.execute(
            channel=channel,
            address=address,
            incoming_text=text or "",
            sender_name=sender_name,
            media=media,
        )

        return {

            "success": True,

            "onboarding": True,

            "reply_sent": bool(reply),

        }

    # mídia de atleta cadastrado: plano do treinador (se aplicável)
    if media is not None:

        reply = await _handle_profile_media(profile, media)

        return {

            "success": True,

            "profile": profile,

            "reply_sent": bool(reply),

        }

    reply = await CoachConversationEvent.execute(
        profile=profile,
        incoming_text=text,
        sender_name=sender_name,
    )

    return {

        "success": True,

        "profile": profile,

        "reply_sent": bool(reply),

    }


async def _handle_profile_media(
    profile: str,
    media: dict,
) -> str:

    runner = RunnerProfileRepository().load(profile)

    if runner.external_coach:

        return await ExternalPlanEvent.execute(
            profile=profile,
            media=media,
        )

    reply = (
        "Recebi sua imagem! 📷 Por enquanto eu só leio planos de "
        "treinador de quem treina com um — e o seu plano é comigo "
        "mesmo. 😉 Se você passou a treinar com um treinador, me "
        "avisa que eu registro."
    )

    await NotificationService.send(
        runner,
        reply,
    )

    return reply


# ==========================================================
# TELEGRAM INBOUND
# ==========================================================

@router.post("/telegram")
async def receive_telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=""),
):

    settings = get_settings()

    secret = settings.telegram_webhook_secret

    if secret and x_telegram_bot_api_secret_token != secret:

        raise HTTPException(
            status_code=401,
            detail="Invalid Telegram secret token",
        )

    update = await request.json()

    print()
    print("=" * 70)
    print("TELEGRAM WEBHOOK RECEBIDO")
    print("=" * 70)
    print(update)
    print("=" * 70)

    message = TelegramInboundParser.message(update)

    if message is None or TelegramInboundParser.is_from_bot(message):

        return {"ignored": True, "reason": "no direct message"}

    chat_id = TelegramInboundParser.chat_id(message)

    if chat_id is None:

        return {"ignored": True, "reason": "no chat id"}

    text = TelegramInboundParser.extract_text(message)

    media = TelegramInboundParser.extract_media(message)

    if not text and not media:

        return {"ignored": True, "reason": "no supported content found"}

    try:

        return await route_inbound(
            channel="telegram",
            address=chat_id,
            text=text,
            media=media,
            sender_name=TelegramInboundParser.sender_name(message),
        )

    except Exception as e:

        print(f"Falha ao processar mensagem Telegram de {chat_id}: {e}")

        return {"success": False, "error": str(e)}