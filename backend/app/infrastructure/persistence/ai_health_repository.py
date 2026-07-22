import json
from pathlib import Path

_STORAGE = (
    Path(__file__)
    .resolve()
    .parents[3]
    / "storage"
)


class AIHealthRepository:
    """Estado do monitor de saúde da IA (contador de falhas seguidas + flag
    de 'já alertou'), persistido pra sobreviver a restart.

    storage/ai_health.json — {"consecutive_failures": int, "alerted": bool}.
    """

    def __init__(self):

        _STORAGE.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.file = _STORAGE / "ai_health.json"

    def load(self) -> dict:

        if not self.file.exists():

            return {"consecutive_failures": 0, "alerted": False}

        with open(
            self.file,
            encoding="utf-8",
        ) as f:

            return json.load(f)

    def save(
        self,
        state: dict,
    ) -> None:

        with open(
            self.file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(state, f)
