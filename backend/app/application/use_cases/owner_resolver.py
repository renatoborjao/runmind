from pathlib import Path

from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


class OwnerResolver:

    @staticmethod
    def resolve(
        owner_id: int,
    ) -> str:

        repository = RunnerProfileRepository()

        storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
        )

        for file in storage.glob("*.json"):

            profile = file.stem

            runner = repository.load(
                profile,
            )

            if (
                getattr(
                    runner,
                    "strava_athlete_id",
                    None,
                )
                == owner_id
            ):

                return profile

        raise Exception(
            f"Nenhum perfil encontrado para owner_id={owner_id}"
        )