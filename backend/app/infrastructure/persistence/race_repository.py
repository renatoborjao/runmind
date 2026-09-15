from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.core.clock import now_local


class RaceRepository:
    """Lista ESTRUTURADA de provas do atleta (uma ou várias), pra o app cadastrar/
    ver/remover. Um arquivo por atleta: storage/races/{profile}.json —
    [{id, name, date(ISO), target_time, created_at}].

    NÃO substitui a periodização: a prova datada MAIS PRÓXIMA continua ancorando
    o plano pelos campos do perfil (target_race/race_date/target_time). Este
    repo é a fonte da LISTA; o RaceService mantém a âncora do perfil em sincronia
    (e reconcilia a prova que o coach setou por conversa). Ver
    [[project_multiplos_objetivos]] e [[feedback_tudo_dinamico]]."""

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "races"
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

    def save(self, profile: str, races: list[dict]) -> None:

        with open(self._file(profile), "w", encoding="utf-8") as f:

            json.dump(races, f, ensure_ascii=False, indent=2)

    def add(
        self,
        profile: str,
        name: str,
        date: str,
        target_time: str | None = None,
    ) -> dict:

        races = self.load(profile)

        record = {
            "id": uuid.uuid4().hex[:12],
            "name": name,
            "date": date,
            "target_time": target_time,
            "created_at": now_local().isoformat(),
        }

        races.append(record)

        self.save(profile, races)

        return record

    def upsert(
        self,
        profile: str,
        name: str,
        date: str,
        target_time: str | None = None,
    ) -> dict:
        """Adiciona a prova se ainda não existe (dedup por data + nome
        normalizado); se existir, completa o tempo-alvo que faltava. Usado pra
        espelhar a prova que o coach registrou por conversa na LISTA do app."""

        def _norm(s: str) -> str:
            return " ".join((s or "").lower().split())

        races = self.load(profile)

        for r in races:

            if r.get("date") == date and _norm(r.get("name")) == _norm(name):

                if target_time and not r.get("target_time"):

                    r["target_time"] = target_time
                    self.save(profile, races)

                return r

        return self.add(profile, name, date, target_time)

    def remove(self, profile: str, race_id: str) -> bool:

        races = self.load(profile)

        kept = [r for r in races if r.get("id") != race_id]

        if len(kept) == len(races):

            return False

        self.save(profile, kept)

        return True
