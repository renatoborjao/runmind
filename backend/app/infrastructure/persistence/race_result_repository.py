import json
from pathlib import Path


class RaceResultRepository:
    """Guarda o RESULTADO de cada prova-alvo cumprida (o debrief registra ao
    reconhecer a prova). É o que deixa o resumo semanal, o recap e afins saberem
    que houve uma PROVA na semana — sem depender do race_date, que o debrief
    consome. Lista append-only por atleta; leitura best-effort."""

    def __init__(self):

        self.storage = (
            Path(__file__)
            .resolve()
            .parents[3]
            / "storage"
            / "race_results"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def load(self, profile: str) -> list[dict]:

        file = self._file(profile)

        if not file.exists():

            return []

        try:

            with open(file, encoding="utf-8") as f:

                data = json.load(f)

            return data if isinstance(data, list) else []

        except (json.JSONDecodeError, OSError):

            return []

    def record(self, profile: str, result: dict) -> None:
        """Grava o resultado da prova. Idempotente por data: se já houver um
        resultado da MESMA data, substitui (evita duplicar num reprocessamento)."""

        results = [
            r for r in self.load(profile) if r.get("date") != result.get("date")
        ]

        results.append(result)

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(results, f, ensure_ascii=False, indent=2)
