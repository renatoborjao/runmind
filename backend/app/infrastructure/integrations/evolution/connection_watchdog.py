import httpx

from app.core.config import get_settings


class ConnectionWatchdog:
    """Autocura da sessão do WhatsApp: quedas transitórias (rede,
    reinício) reconectam sozinhas via /instance/connect. Logout de
    verdade não tem cura automática — exige escanear QR de novo."""

    @staticmethod
    async def check_and_heal() -> str:

        settings = get_settings()

        headers = {"apikey": settings.evolution_api_key}

        base = (
            f"{settings.evolution_api_url}/instance"
        )

        instance = settings.evolution_instance

        async with httpx.AsyncClient(timeout=15) as client:

            response = await client.get(
                f"{base}/connectionState/{instance}",
                headers=headers,
            )

            response.raise_for_status()

            state = response.json()["instance"]["state"]

            if state == "open":

                return state

            print(
                f"WhatsApp '{instance}' em '{state}' — "
                f"tentando reconectar..."
            )

            await client.get(
                f"{base}/connect/{instance}",
                headers=headers,
            )

            return state
