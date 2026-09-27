from __future__ import annotations

import httpx

from app.core.config import get_settings


class WebhookService:

    BASE_URL = "https://www.strava.com/api/v3/push_subscriptions"

    VERIFY_TOKEN = "runmind123"

    @classmethod
    async def register(
        cls,
        callback_url: str,
    ):

        settings = get_settings()

        async with httpx.AsyncClient(
            timeout=30,
        ) as client:

            response = await client.post(

                cls.BASE_URL,

                data={

                    "client_id": settings.strava_client_id,

                    "client_secret": settings.strava_client_secret,

                    "callback_url": callback_url,

                    "verify_token": cls.VERIFY_TOKEN,

                },

            )

        response.raise_for_status()

        return response.json()

    @classmethod
    async def subscriptions(cls):

        settings = get_settings()

        async with httpx.AsyncClient(
            timeout=30,
        ) as client:

            response = await client.get(

                cls.BASE_URL,

                params={

                    "client_id": settings.strava_client_id,

                    "client_secret": settings.strava_client_secret,

                },

            )

        response.raise_for_status()

        return response.json()

    @classmethod
    async def delete(
        cls,
        subscription_id: int,
    ):
        """Apaga a inscrição. O Strava exige o id no CAMINHO
        (/push_subscriptions/{id}) — como query param dava 4xx (e 500 no app)."""

        settings = get_settings()

        async with httpx.AsyncClient(
            timeout=30,
        ) as client:

            response = await client.delete(

                f"{cls.BASE_URL}/{subscription_id}",

                params={

                    "client_id": settings.strava_client_id,

                    "client_secret": settings.strava_client_secret,

                },

            )

        response.raise_for_status()

        return {

            "deleted": True

        }

    @classmethod
    async def repoint(
        cls,
        callback_url: str,
    ):
        """Garante UMA inscrição apontando pra `callback_url`. O Strava aceita
        só uma por app — registrar com uma velha no lugar dá 400 — então apaga
        as que apontam pra outro lugar e cria a nova. Idempotente: se já está
        certa, não mexe. (A inscrição ficou no ngrok velho por semanas depois
        da migração pra Oracle; ver [[project_strava_rename]].)"""

        current = await cls.subscriptions()

        if any(s.get("callback_url") == callback_url for s in current):

            return {"changed": False, "subscriptions": current}

        removed = []

        for sub in current:

            await cls.delete(sub["id"])

            removed.append(sub.get("callback_url"))

        created = await cls.register(callback_url)

        return {"changed": True, "removed": removed, "created": created}
