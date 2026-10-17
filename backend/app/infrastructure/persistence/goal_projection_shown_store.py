"""O que o atleta JÁ viu do "rumo à meta" no resumo de domingo — pra só repetir a
projeção quando há novidade (ou passou um mês). storage/goal_projection_shown/
{profile}.json — o último snapshot mostrado + a data. Gitignored (dado de atleta)."""

import json
from pathlib import Path


class GoalProjectionShownStore:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "goal_projection_shown"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def load(self, profile: str) -> dict | None:
        """O último snapshot mostrado ({"date", "seconds", ...}) ou None."""

        file = self._file(profile)

        if not file.exists():

            return None

        try:

            data = json.loads(file.read_text(encoding="utf-8"))

            return data if isinstance(data, dict) else None

        except Exception:

            return None

    def save(self, profile: str, snapshot: dict, shown_on: str) -> None:
        """Grava o snapshot que acabou de ser mostrado, com a data (ISO)."""

        payload = {**snapshot, "date": shown_on}

        self._file(profile).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
