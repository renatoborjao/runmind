"""sRPE por sessão — storage/session_rpe/{profile}.json.

Guarda a série de sRPE gravados + UM 'pendente' (o treino que acabou de sair e
está esperando o atleta responder o RPE). O pendente é o que permite
interpretar um '7' solto como resposta de RPE só quando faz sentido (logo após
o feedback), e não confundir com qualquer número. Gitignored (dado de atleta)."""

import json
from dataclasses import asdict
from pathlib import Path

from app.domain.entities.session_rpe import SessionRpe

_MAX = 60


class SessionRpeRepository:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "session_rpe"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _read(self, profile: str) -> dict:

        file = self.storage / f"{profile}.json"

        if not file.exists():

            return {"pending": None, "sessions": []}

        with open(file, encoding="utf-8") as f:

            return json.load(f)

    def _write(self, profile: str, data: dict) -> None:

        file = self.storage / f"{profile}.json"

        with open(file, "w", encoding="utf-8") as f:

            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---- pendente (treino aguardando RPE) ----

    def set_pending(
        self, profile: str, activity_id: int, day: str, duration_min: float
    ) -> None:

        data = self._read(profile)

        data["pending"] = {
            "activity_id": activity_id,
            "day": day,
            "duration_min": duration_min,
        }

        self._write(profile, data)

    def get_pending(self, profile: str) -> dict | None:

        return self._read(profile).get("pending")

    def clear_pending(self, profile: str) -> None:

        data = self._read(profile)

        if data.get("pending") is not None:

            data["pending"] = None

            self._write(profile, data)

    # ---- sessões gravadas ----

    def record(self, profile: str, session: SessionRpe) -> None:
        """Grava o sRPE e limpa o pendente. Um RPE por atividade (regravar o
        mesmo treino substitui)."""

        data = self._read(profile)

        sessions = [
            s for s in data.get("sessions", [])
            if s.get("activity_id") != session.activity_id
        ]

        sessions.append(asdict(session))

        data["sessions"] = sessions[-_MAX:]

        data["pending"] = None

        self._write(profile, data)

    def load_sessions(self, profile: str) -> list[SessionRpe]:

        return [
            SessionRpe(**record)
            for record in self._read(profile).get("sessions", [])
        ]

    def latest(self, profile: str) -> SessionRpe | None:

        sessions = self.load_sessions(profile)

        return sessions[-1] if sessions else None
