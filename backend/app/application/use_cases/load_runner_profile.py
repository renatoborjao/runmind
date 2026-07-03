from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)


class LoadRunnerProfile:

    @staticmethod
    def execute(
        profile: str = "renato",
    ) -> RunnerProfile:

        repository = RunnerProfileRepository()

        return repository.load(profile)