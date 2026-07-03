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

        settings = get_settings()

        async with httpx.AsyncClient(
            timeout=30,
        ) as client:

            response = await client.delete(

                cls.BASE_URL,

                params={

                    "client_id": settings.strava_client_id,

                    "client_secret": settings.strava_client_secret,

                    "id": subscription_id,

                },

            )

        response.raise_for_status()

        return {

            "deleted": True

        }