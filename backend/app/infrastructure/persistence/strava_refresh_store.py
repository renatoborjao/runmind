"""Marca que o atleta JÁ recebeu o plano regenerado ao conectar o Strava
DEPOIS do cadastro (late connector). Uma vez só: reconexões não re-disparam
o plano nem a mensagem — o plano de domingo cuida das semanas seguintes."""

import json
from pathlib import Path

_STORAGE = (
    Path(__file__).resolve().parents[3] / "storage" / "strava_refresh"
)


class StravaRefreshStore:

    @staticmethod
    def _file(profile: str) -> Path:

        return _STORAGE / f"{profile}.json"

    @staticmethod
    def is_done(profile: str) -> bool:

        return StravaRefreshStore._file(profile).exists()

    @staticmethod
    def mark(profile: str) -> None:

        _STORAGE.mkdir(parents=True, exist_ok=True)

        StravaRefreshStore._file(profile).write_text(
            json.dumps({"done": True}),
            encoding="utf-8",
        )
