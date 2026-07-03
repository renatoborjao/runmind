import json
from pathlib import Path


class OnboardingStateRepository:
    """Estado do questionário de onboarding, um arquivo por telefone:
    storage/onboarding/{telefone}.json"""

    def __init__(self):

        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
            / "onboarding"
        )

        self.storage.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load(
        self,
        phone: str,
    ) -> dict | None:

        file = self.storage / f"{phone}.json"

        if not file.exists():

            return None

        with open(
            file,
            encoding="utf-8",
        ) as f:

            return json.load(f)

    def save(
        self,
        phone: str,
        state: dict,
    ) -> None:

        file = self.storage / f"{phone}.json"

        with open(
            file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                state,
                f,
                ensure_ascii=False,
                indent=2,
            )

    def delete(
        self,
        phone: str,
    ) -> None:

        file = self.storage / f"{phone}.json"

        if file.exists():

            file.unlink()
