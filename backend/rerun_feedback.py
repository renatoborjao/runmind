"""Reprocessa o feedback de um treino específico e reenvia ao atleta.

Uso pontual (mesmo caminho do webhook: detalhe + streams + evento):
    python rerun_feedback.py <profile> <activity_id>
"""

import asyncio
import sys

from app.application.events.training_completed import (
    TrainingCompletedEvent,
)
from app.infrastructure.integrations.strava.client import StravaClient


async def main(profile: str, activity_id: int) -> None:

    client = StravaClient(profile)

    activity = await client.get_activity(activity_id)

    try:

        activity.raw["_streams"] = await client.get_activity_streams(
            activity_id,
        )

    except Exception as e:

        print(f"Streams indisponíveis: {e}")

    result = await TrainingCompletedEvent.execute(
        profile=profile,
        activity=activity,
    )

    print("=" * 60)
    print(result["message"])
    print("=" * 60)
    print("Mensagem reenviada.")


if __name__ == "__main__":

    asyncio.run(main(sys.argv[1], int(sys.argv[2])))
