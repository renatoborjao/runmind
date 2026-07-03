from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request

from app.application.events.coach_conversation import (
    CoachConversationEvent,
)
from app.application.events.training_completed import (
    TrainingCompletedEvent,
)
from app.application.use_cases.owner_resolver import (
    OwnerResolver,
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

    if not text:

        return {

            "ignored": True,

            "reason": "no text content found",

        }

    phone = PhoneNormalizer.normalize(raw_phone)

    profile = RunnerProfileRepository().find_by_phone(phone)

    if profile is None:

        print(f"Nenhum profile encontrado para phone={phone}")

        return {

            "ignored": True,

            "reason": "unknown phone",

        }

    reply = await CoachConversationEvent.execute(
        profile=profile,
        incoming_text=text,
        sender_name=data.get("pushName", ""),
    )

    return {

        "success": True,

        "profile": profile,

        "reply_sent": bool(reply),

    }