from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.core.clock import now_local

# quantas notificações guardar por atleta (as mais novas). A central do app é
# um FEED recente, não um arquivo eterno — o Telegram segue com o histórico.
_MAX_ITEMS = 100


class AppNotificationRepository:
    """Central de notificações DENTRO do app: espelha os toques PROATIVOS do
    coach (os mesmos que saem no Telegram) pra o atleta ver na tela, com estado
    lido/não-lido. Um arquivo por atleta: storage/app_notifications/{profile}.json.

    A CHAVE é a mesma do login (`current_profile` == `runner.id`), então o que é
    gravado no envio é lido pela tela do mesmo atleta. Best-effort no envio:
    falhar aqui NUNCA pode derrubar a mensagem que já saiu no canal."""

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "app_notifications"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def load(self, profile: str) -> list[dict]:
        """Notificações do atleta, das mais novas pras mais antigas."""

        file = self._file(profile)

        if not file.exists():

            return []

        try:

            with open(file, encoding="utf-8") as f:

                data = json.load(f)

            return data if isinstance(data, list) else []

        except (json.JSONDecodeError, OSError):

            return []

    def _save(self, profile: str, items: list[dict]) -> None:

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(items[:_MAX_ITEMS], f, ensure_ascii=False, indent=2)

    def append(
        self,
        profile: str,
        text: str,
        title: str | None = None,
        kind: str | None = None,
    ) -> dict:
        """Registra uma notificação nova (fica no topo, não-lida)."""

        record = {
            "id": uuid.uuid4().hex[:12],
            "kind": kind,
            "title": title,
            "text": text,
            "created_at": now_local().isoformat(),
            "read": False,
        }

        items = self.load(profile)

        items.insert(0, record)

        self._save(profile, items)

        return record

    def unread_count(self, profile: str) -> int:

        return sum(1 for i in self.load(profile) if not i.get("read"))

    def mark_read(self, profile: str, ids: list[str] | None = None) -> None:
        """Marca como lidas: `ids` específicas, ou TODAS quando None."""

        items = self.load(profile)

        wanted = set(ids) if ids is not None else None

        changed = False

        for item in items:

            if wanted is None or item.get("id") in wanted:

                if not item.get("read"):

                    item["read"] = True

                    changed = True

        if changed:

            self._save(profile, items)
