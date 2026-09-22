from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.core.clock import now_local


class ActivityCommentRepository:
    """Comentários nas atividades (estilo Strava). Guardados sob o DONO da
    atividade: storage/activity_comments/{owner}.json, chave da atividade ->
    lista de {id, author, author_name, text, at}. Leve e best-effort."""

    def __init__(self):

        self.dir = (
            Path(__file__).resolve().parents[3] / "storage" / "activity_comments"
        )

        self.dir.mkdir(parents=True, exist_ok=True)

    def _file(self, owner: str) -> Path:

        return self.dir / f"{owner}.json"

    def _load_all(self, owner: str) -> dict:

        f = self._file(owner)

        if not f.exists():

            return {}

        try:

            with open(f, encoding="utf-8") as fh:

                return json.load(fh)

        except (json.JSONDecodeError, OSError):

            return {}

    def _save_all(self, owner: str, data: dict) -> None:

        with open(self._file(owner), "w", encoding="utf-8") as fh:

            json.dump(data, fh, ensure_ascii=False, indent=2)

    def list(self, owner: str, key: str) -> list[dict]:

        return self._load_all(owner).get(key, [])

    def counts(self, owner: str) -> dict[str, int]:
        """{chave -> nº de comentários} do dono — pro contador no feed."""

        return {k: len(v) for k, v in self._load_all(owner).items() if v}

    def add(self, owner: str, key: str, author: str, author_name: str, text: str) -> dict:

        data = self._load_all(owner)

        comment = {
            "id": uuid.uuid4().hex[:12],
            "author": author,
            "author_name": author_name,
            "text": text.strip()[:500],
            "at": now_local().isoformat(),
        }

        data.setdefault(key, []).append(comment)

        self._save_all(owner, data)

        return comment

    def delete(self, owner: str, key: str, comment_id: str, requester: str) -> bool:
        """Remove um comentário. Pode: o AUTOR do comentário OU o DONO da
        atividade (modera o próprio mural). Devolve True se removeu."""

        data = self._load_all(owner)

        items = data.get(key, [])

        for i, c in enumerate(items):

            if c.get("id") == comment_id:

                if requester != c.get("author") and requester != owner:

                    return False

                items.pop(i)

                if items:

                    data[key] = items

                else:

                    data.pop(key, None)

                self._save_all(owner, data)

                return True

        return False
