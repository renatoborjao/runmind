from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.infrastructure.integrations.strava.mapper import (
    StravaMapper,
)
from app.infrastructure.storage.token_store import (
    TokenStore,
)


class StravaClient:

    BASE_URL = "https://www.strava.com/api/v3"

    TOKEN_URL = "https://www.strava.com/oauth/token"

    def __init__(
        self,
        profile: str = "renato",
    ):

        self.settings = get_settings()

        self.token_store = TokenStore(
            profile
        )

    async def _get_access_token(self) -> str:

        print("========================================")
        print("1 - Iniciando obtenção do Access Token")

        tokens = self.token_store.load()

        if not tokens:

            raise Exception(
                "Nenhum token encontrado."
            )

        print("2 - Token encontrado")
        print("3 - Solicitando novo token ao Strava")

        async with httpx.AsyncClient(
            timeout=10,
        ) as client:

            response = await client.post(

                self.TOKEN_URL,

                json={

                    "client_id": self.settings.strava_client_id,

                    "client_secret": self.settings.strava_client_secret,

                    "refresh_token": tokens["refresh_token"],

                    "grant_type": "refresh_token",

                },

            )

        print("4 - Resposta recebida do Strava")

        response.raise_for_status()

        data = response.json()

        self.token_store.save(

            {

                "access_token": data["access_token"],

                "refresh_token": data["refresh_token"],

                "expires_at": data["expires_at"],

            }

        )

        print("5 - Token salvo")

        return data["access_token"]

    async def get_latest_activity(self):

        activities = await self.get_last_activities(
            limit=1,
        )

        if not activities:

            return None

        return activities[0]

    async def get_last_activities(
        self,
        limit: int = 30,
    ):

        print(f"7 - Buscando {limit} atividades")

        access_token = await self._get_access_token()

        print("8 - Access Token obtido")

        async with httpx.AsyncClient(
            timeout=10,
        ) as client:

            response = await client.get(

                f"{self.BASE_URL}/athlete/activities",

                headers={

                    "Authorization": f"Bearer {access_token}"

                },

                params={

                    "per_page": limit

                },

            )

        print("9 - Resposta da API de atividades")

        response.raise_for_status()

        data = response.json()

        print(f"10 - {len(data)} atividades recebidas")

        return [

            StravaMapper.to_activity(
                activity
            )

            for activity in data

        ]

    async def get_activity(
        self,
        activity_id: int,
    ):

        print(f"11 - Buscando atividade {activity_id}")

        access_token = await self._get_access_token()

        print("12 - Access Token obtido")

        async with httpx.AsyncClient(
            timeout=10,
        ) as client:

            response = await client.get(

                f"{self.BASE_URL}/activities/{activity_id}",

                headers={

                    "Authorization": f"Bearer {access_token}"

                },

            )

        print("13 - Resposta da API da atividade")

        response.raise_for_status()

        data = response.json()

        print("14 - Atividade carregada")

        return StravaMapper.to_activity(
            data
        )

    async def get_activity_streams(
        self,
        activity_id: int,
        keys: str = "time,distance,velocity_smooth,heartrate,cadence,moving",
    ) -> dict:
        """Séries segundo a segundo do treino (velocidade, FC, distância).
        É o único dado que revela tiros curtos (ex.: 8x400m) que os splits
        por km borram. Retorna {tipo: [valores]}; {} se indisponível."""

        access_token = await self._get_access_token()

        async with httpx.AsyncClient(
            timeout=15,
        ) as client:

            response = await client.get(
                f"{self.BASE_URL}/activities/{activity_id}/streams",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                params={
                    "keys": keys,
                    "key_by_type": "true",
                },
            )

        response.raise_for_status()

        data = response.json()

        return {
            stream_type: payload.get("data", [])
            for stream_type, payload in data.items()
        }