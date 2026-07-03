from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
import httpx

from app.application.services.strava.webhook_service import (
    WebhookService,
)
from app.core.config import get_settings
from app.infrastructure.integrations.strava.client import (
    StravaClient,
)
from app.infrastructure.storage.token_store import (
    TokenStore,
)

router = APIRouter(
    prefix="/strava",
    tags=["Strava"],
)


# ==========================================================
# OAUTH
# ==========================================================

@router.get("/connect")
async def connect():

    settings = get_settings()

    url = (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={settings.strava_client_id}"
        "&response_type=code"
        "&redirect_uri=http://127.0.0.1:8000/api/v1/strava/callback"
        "&approval_prompt=force"
        "&scope=read,activity:read_all"
    )

    return RedirectResponse(url)


@router.get("/callback")
async def callback(
    code: str,
):

    settings = get_settings()

    async with httpx.AsyncClient() as client:

        response = await client.post(

            "https://www.strava.com/oauth/token",

            data={

                "client_id": settings.strava_client_id,

                "client_secret": settings.strava_client_secret,

                "code": code,

                "grant_type": "authorization_code",

            },

        )

    if response.status_code != 200:

        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    data = response.json()

    TokenStore().save(

        {

            "access_token": data["access_token"],

            "refresh_token": data["refresh_token"],

            "expires_at": data["expires_at"],

        }

    )

    return {

        "message": "Strava conectado com sucesso.",

        "saved": True,

    }


# ==========================================================
# ATHLETE
# ==========================================================

@router.get("/me")
async def me():

    client = StravaClient()

    access_token = await client._get_access_token()

    async with httpx.AsyncClient(
        timeout=10,
    ) as http:

        response = await http.get(

            "https://www.strava.com/api/v3/athlete",

            headers={

                "Authorization": f"Bearer {access_token}"

            },

        )

    response.raise_for_status()

    athlete = response.json()

    return {

        "id": athlete["id"],

        "username": athlete.get("username"),

        "firstname": athlete.get("firstname"),

        "lastname": athlete.get("lastname"),

        "city": athlete.get("city"),

        "country": athlete.get("country"),

    }


# ==========================================================
# WEBHOOKS
# ==========================================================

@router.post("/register-webhook")
async def register_webhook():

    callback_url = (
        "https://unopened-employed-cedar.ngrok-free.dev"
        "/api/v1/webhooks/strava"
    )

    return await WebhookService.register(
        callback_url,
    )


@router.get("/subscriptions")
async def subscriptions():

    return await WebhookService.subscriptions()


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(
    subscription_id: int,
):

    return await WebhookService.delete(
        subscription_id,
    )