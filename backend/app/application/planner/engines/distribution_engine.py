from app.domain.entities.runner_profile import RunnerProfile


class DistributionEngine:

    @staticmethod
    def execute(
        runner: RunnerProfile,
    ) -> list[str]:

        return runner.preferred_running_days