"""Guarda as últimas mensagens AUTOMÁTICAS que o coach enviou ao atleta
(análise pós-treino, briefing matinal, plano da semana, review) — fora do
fluxo de chat. É lido pelo ConversationContextBuilder pra o coach LEMBRAR do
que disse quando o atleta comentar depois ("você analisou meu treino")."""

import json
from datetime import UTC, datetime
from pathlib import Path

# quantas mensagens enviadas guardar por atleta
_MAX_ENTRIES = 10


class CoachOutboxRepository:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "coach_outbox"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def _load(self, profile: str) -> list[dict]:

        file = self._file(profile)

        if not file.exists():

            return []

        try:

            return json.loads(file.read_text(encoding="utf-8"))

        except (json.JSONDecodeError, OSError):

            return []

    def append(self, profile: str, text: str) -> None:

        entries = self._load(profile)

        entries.append(
            {
                "text": text,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        entries = entries[-_MAX_ENTRIES:]

        self._file(profile).write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def recent(self, profile: str, limit: int = 3) -> list[dict]:

        return self._load(profile)[-limit:]
