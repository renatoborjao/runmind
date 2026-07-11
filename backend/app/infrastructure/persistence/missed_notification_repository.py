import json
from pathlib import Path


class MissedNotificationRepository:
    """Guarda, por atleta, a última data de treino-furado já avisada — pra
    a passada matinal não mandar duas vezes a mesma mensagem de 'furou
    ontem'."""

    def __init__(self):

        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
            / "missed"
        )

        self.storage.mkdir(
            parents=True,
            exist_ok=True,
        )

    def last_notified(
        self,
        profile: str,
    ) -> str | None:

        file = self.storage / f"{profile}.json"

        if not file.exists():

            return None

        with open(file, encoding="utf-8") as f:

            return json.load(f).get("date")

    def mark(
        self,
        profile: str,
        missed_date: str,
    ) -> None:

        file = self.storage / f"{profile}.json"

        with open(file, "w", encoding="utf-8") as f:

            json.dump({"date": missed_date}, f, ensure_ascii=False)
