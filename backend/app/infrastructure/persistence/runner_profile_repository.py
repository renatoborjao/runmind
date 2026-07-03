import json
from dataclasses import fields
from pathlib import Path

from app.domain.entities.runner_profile import RunnerProfile
from app.infrastructure.integrations.evolution.phone_normalizer import (
    PhoneNormalizer,
)


class RunnerProfileRepository:

    def __init__(self):

        # um arquivo por atleta: storage/profiles/{profile}.json
        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
            / "profiles"
        )

        self.storage.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load(
        self,
        profile: str = "renato",
    ) -> RunnerProfile:

        file = self.storage / f"{profile}.json"

        with open(
            file,
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        # ignora chaves do JSON que a entidade (ainda) não conhece
        known = {field.name for field in fields(RunnerProfile)}

        return RunnerProfile(**{
            key: value
            for key, value in data.items()
            if key in known
        })

    def update_injuries(
        self,
        profile: str,
        injuries: list[str],
    ) -> None:
        """Regrava apenas a chave `injuries`, preservando chaves do JSON
        que a entidade não conhece (notifications, timezone...)."""

        file = self.storage / f"{profile}.json"

        with open(
            file,
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        data["injuries"] = injuries

        with open(
            file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2,
            )

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