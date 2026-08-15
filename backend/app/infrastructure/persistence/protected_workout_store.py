"""Workouts que a VARREDURA de órfãos (`sweep_orphan_workouts`) nunca deve
apagar — pushes avulsos/de PROVA que não são sessão do plano semanal e por isso
não entram no `keep_ids` do plano. Sem isto, um treino de prova empurrado pra
uma data futura seria varrido no push de domingo seguinte.

storage/protected_workouts/{profile}.json (lista de workout_ids). Gitignored."""

import json
from pathlib import Path


class ProtectedWorkoutStore:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "protected_workouts"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def ids(self, profile: str) -> set:

        file = self._file(profile)

        if not file.exists():

            return set()

        try:

            return set(json.loads(file.read_text(encoding="utf-8")))

        except Exception:

            return set()

    def add(self, profile: str, workout_id) -> None:

        if workout_id is None:

            return

        ids = self.ids(profile)

        ids.add(workout_id)

        self._file(profile).write_text(
            json.dumps(sorted(ids, key=str)), encoding="utf-8"
        )
