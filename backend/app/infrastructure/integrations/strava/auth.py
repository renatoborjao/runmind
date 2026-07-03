from __future__ import annotations

import httpx

from app.core.config import get_settings


class StravaAuth:
    TOKEN_URL = "https://www.strava.com/oauth/token"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def get_access_token(self) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self.TOKEN_URL,
                json={
                    "client_id": self.settings.strava_client_id,
                    "client_secret": self.settings.strava_client_secret,
                    "refresh_token": self.settings.strava_refresh_token,
                    "grant_type": "refresh_token",
                },
            )

        response.raise_for_status()

        data = response.json()

        return data["access_token"]