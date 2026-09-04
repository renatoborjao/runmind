"""Uso de tokens do Gemini por atleta — storage/token_usage/{profile}.jsonl.

Uma LINHA por chamada (append barato, sem read-modify-write → robusto a
concorrência de tasks async). A agregação é feita na LEITURA. Observação/
best-effort, gitignored (dado de atleta). Lido via GET /debug/usage/{profile}.
Ver [[project_consumo_tokens]]."""

import json
from pathlib import Path

# janela ampla; a leitura apara pro fim pra o arquivo não crescer sem limite
_MAX_LINES = 5000


class TokenUsageRepository:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "token_usage"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.jsonl"

    def append(self, profile: str, record: dict) -> None:
        """Anexa 1 chamada. Best-effort: o chamador engole exceção (o medidor
        NUNCA pode derrubar uma chamada ao Gemini)."""

        with open(self._file(profile), "a", encoding="utf-8") as f:

            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read(self, profile: str) -> list[dict]:

        file = self._file(profile)

        if not file.exists():

            return []

        out: list[dict] = []

        try:

            with open(file, encoding="utf-8") as f:

                for line in f:

                    line = line.strip()

                    if not line:

                        continue

                    try:

                        out.append(json.loads(line))

                    except json.JSONDecodeError:

                        continue

        except OSError:

            return []

        return out[-_MAX_LINES:]

    def profiles(self) -> list[str]:

        return sorted(p.stem for p in self.storage.glob("*.jsonl"))
