from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


class OwnerResolver:

    @staticmethod
    def resolve(
        owner_id: int,
    ) -> str:

        repository = RunnerProfileRepository()

        for profile, runner in repository._valid_profiles():

            if runner.strava_athlete_id == owner_id:

                return profile

        raise Exception(
            f"Nenhum perfil encontrado para owner_id={owner_id}"
        )
