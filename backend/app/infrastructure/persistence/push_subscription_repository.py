from __future__ import annotations

import json
from pathlib import Path

from app.core.clock import now_local


class PushSubscriptionRepository:
    """Inscrições de Web Push do atleta (uma por navegador/dispositivo em que ele
    ligou as notificações). Um arquivo por atleta:
    storage/push_subscriptions/{profile}.json — lista de PushSubscription do
    navegador (endpoint + keys p256dh/auth).

    A CHAVE é a do login (`current_profile` == `runner.id`), a mesma usada no
    envio. Dedup por endpoint (o mesmo aparelho re-registrando não duplica)."""

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "push_subscriptions"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def list(self, profile: str) -> list[dict]:

        file = self._file(profile)

        if not file.exists():

            return []

        try:

            with open(file, encoding="utf-8") as f:

                data = json.load(f)

            return data if isinstance(data, list) else []

        except (json.JSONDecodeError, OSError):

            return []

    def _save(self, profile: str, subs: list[dict]) -> None:

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(subs, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _endpoint(sub: dict) -> str | None:

        return (sub or {}).get("endpoint")

    def add(self, profile: str, subscription: dict) -> None:
        """Guarda a inscrição (substitui a do mesmo endpoint, se já existia)."""

        endpoint = self._endpoint(subscription)

        if not endpoint:

            return

        subs = [s for s in self.list(profile) if self._endpoint(s) != endpoint]

        subs.append({
            "endpoint": endpoint,
            "keys": (subscription or {}).get("keys") or {},
            "added_at": now_local().isoformat(),
        })

        self._save(profile, subs)

    def remove(self, profile: str, endpoint: str) -> None:
        """Remove uma inscrição (o atleta desligou, ou o push service disse que
        ela morreu — 404/410)."""

        subs = [s for s in self.list(profile) if self._endpoint(s) != endpoint]

        self._save(profile, subs)
