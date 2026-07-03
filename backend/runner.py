import asyncio
import sys

from app.application.events.training_completed import (
    TrainingCompletedEvent,
)


async def main():

    profile = "renato"

    if len(sys.argv) > 1:

        profile = sys.argv[1]

    print()

    print("=" * 60)
    print("🏃 RUNMIND")
    print("=" * 60)
    print()

    print(f"Atleta: {profile}")

    print()

    result = await TrainingCompletedEvent.execute(
        profile=profile,
    )

    print(result["message"])

    print()

    print("=" * 60)
    print("FINALIZADO")
    print("=" * 60)


if __name__ == "__main__":

    asyncio.run(main())