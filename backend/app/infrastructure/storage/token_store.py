from __future__ import annotations

import json
from pathlib import Path


class TokenStore:

    BASE_DIR = Path(__file__).resolve().parents[3]

    def __init__(
        self,
        profile: str = "renato",
    ):

        self.file = (
            self.BASE_DIR
            / "storage"
            / f"{profile}_tokens.json"
        )

        self.file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def save(
        self,
        data: dict,
    ) -> None:

        with open(
            self.file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                data,
                f,
                indent=4,
            )

    def load(
        self,
    ) -> dict | None:

        if not self.file.exists():

            return None

        with open(
            self.file,
            "r",
            encoding="utf-8",
        ) as f:

            return json.load(f)