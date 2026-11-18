"""Renomeações do Strava JÁ APLICADAS nas últimas horas — pra o webhook
perceber quando o nome do plano é SOBRESCRITO logo depois (caso de 18/11: o
app do Strava do atleta, aberto com a tela antiga, salvou a atividade 11 s
depois e voltou 'Corrida matinal'). Guardado por id da atividade NO STRAVA
(é o que o webhook traz), com o perfil e o nome aplicado. Reaplicação é UMA
vez só por atividade — nunca briga em loop com outro app. Expira em 24h.
Ver [[project_strava_rename]]."""

import json
import time
from pathlib import Path

_STORAGE = (
    Path(__file__).resolve().parents[3] / "storage" / "applied_strava_rename"
)

# depois disso, um nome genérico de volta não é mais "reversão da nossa troca"
MAX_AGE_SECONDS = 24 * 3600


class AppliedStravaRenameStore:

    @staticmethod
    def _file() -> Path:

        return _STORAGE / "applied.json"

    @staticmethod
    def _load() -> dict:

        file = AppliedStravaRenameStore._file()

        if not file.exists():

            return {}

        try:

            data = json.loads(file.read_text(encoding="utf-8"))

        except (OSError, json.JSONDecodeError):

            return {}

        return data if isinstance(data, dict) else {}

    @staticmethod
    def _save(data: dict) -> None:

        now = time.time()

        # poda: só o que ainda está na janela
        data = {
            k: v for k, v in data.items()
            if now - v.get("renamed_at", 0) <= MAX_AGE_SECONDS
        }

        file = AppliedStravaRenameStore._file()

        if not data:

            file.unlink(missing_ok=True)

            return

        _STORAGE.mkdir(parents=True, exist_ok=True)

        file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def record(strava_activity_id, profile: str, name: str) -> None:
        """Acabamos de pôr `name` nesta atividade do Strava."""

        data = AppliedStravaRenameStore._load()

        data[str(strava_activity_id)] = {
            "profile": profile,
            "name": name,
            "renamed_at": time.time(),
            "reapplied": False,
        }

        AppliedStravaRenameStore._save(data)

    @staticmethod
    def get(strava_activity_id) -> dict | None:
        """O registro desta atividade, se ainda está na janela de 24h."""

        item = AppliedStravaRenameStore._load().get(str(strava_activity_id))

        if not item:

            return None

        if time.time() - item.get("renamed_at", 0) > MAX_AGE_SECONDS:

            return None

        return item

    @staticmethod
    def mark_reapplied(strava_activity_id) -> None:

        data = AppliedStravaRenameStore._load()

        key = str(strava_activity_id)

        if key in data:

            data[key]["reapplied"] = True

            AppliedStravaRenameStore._save(data)

    @staticmethod
    def forget(strava_activity_id) -> None:

        data = AppliedStravaRenameStore._load()

        if data.pop(str(strava_activity_id), None) is not None:

            AppliedStravaRenameStore._save(data)
