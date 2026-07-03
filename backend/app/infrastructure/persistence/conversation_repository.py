import json
from datetime import UTC, datetime
from pathlib import Path

MAX_TURNS_PERSISTED = 200


class ConversationRepository:

    def __init__(self):

        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
            / "conversations"
        )

        self.storage.mkdir(
            parents=True,
            exist_ok=True,
        )

    def load(
        self,
        profile: str,
    ) -> list[dict]:

        file = self.storage / f"{profile}.json"

        if not file.exists():

            return []

        with open(
            file,
            encoding="utf-8",
        ) as f:

            return json.load(f)

    def append_turn(
        self,
        profile: str,
        role: str,
        text: str,
    ) -> None:

        turns = self.load(profile)

        turns.append(
            {
                "role": role,
                "text": text,
                "timestamp": datetime.now(
                    UTC,
                ).isoformat(),
            }
        )

        turns = turns[-MAX_TURNS_PERSISTED:]

        file = self.storage / f"{profile}.json"

        with open(
            file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                turns,
                f,
                ensure_ascii=False,
                indent=2,
            )

    def recent_turns(
        self,
        profile: str,
        limit: int = 20,
    ) -> list[dict]:

        return self.load(profile)[-limit:]
