import json
from pathlib import Path

from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.integrations.evolution.phone_normalizer import (
    PhoneNormalizer,
)


class RunnerProfileRepository:

    def __init__(self):

        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
        )

    def load(
        self,
        profile: str = "runner_profile",
    ) -> RunnerProfile:

        file = self.storage / f"{profile}.json"

        with open(
            file,
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        return RunnerProfile(**data)

    def find_by_phone(
        self,
        phone: str,
    ) -> str | None:

        target = PhoneNormalizer.normalize(phone)

        for profile, runner in self._valid_profiles():

            if PhoneNormalizer.normalize(runner.phone) == target:

                return profile

        return None

    def list_all(
        self,
    ) -> list[str]:

        return [
            profile
            for profile, _ in self._valid_profiles()
        ]

    def _valid_profiles(
        self,
    ):

        for file in self.storage.glob("*.json"):

            profile = file.stem

            try:

                runner = self.load(profile)

            except Exception:

                continue

            yield profile, runner