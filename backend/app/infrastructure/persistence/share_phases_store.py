"""Cache do EXECUTADO fase a fase de um treino estruturado (voltas do relógio
pareadas com os passos do plano) pro card "Plano × feito" do compartilhar —
storage/share_phases/{profile}.json. Buscar as voltas no Garmin custa uma ida à
API; o treino não muda depois de feito, então guarda por corrida (data + km).

Guarda também o "não deu" (sem voltas / pareamento incerto) pra não bater no
Garmin toda vez que o atleta abre o compartilhar; ERRO de rede NÃO é guardado
(tenta de novo na próxima). Ver [[project_app_atleta]]."""

import json
from pathlib import Path

_STORAGE = Path(__file__).resolve().parents[3] / "storage" / "share_phases"

# corridas guardadas por atleta (as mais recentes ficam)
_MAX_ENTRIES = 200


class SharePhasesStore:

    @staticmethod
    def _file(profile: str) -> Path:

        return _STORAGE / f"{profile}.json"

    @staticmethod
    def key(date_iso: str, km: float) -> str:

        return f"{date_iso[:10]}|{round(km, 1)}"

    @staticmethod
    def _load(profile: str) -> dict:

        file = SharePhasesStore._file(profile)

        if not file.exists():

            return {}

        try:

            data = json.loads(file.read_text(encoding="utf-8"))

        except (OSError, json.JSONDecodeError):

            return {}

        return data if isinstance(data, dict) else {}

    @staticmethod
    def get(profile: str, date_iso: str, km: float) -> tuple[bool, list | None]:
        """(achou_no_cache, fases). Fases None = já sabemos que não dá."""

        data = SharePhasesStore._load(profile)

        key = SharePhasesStore.key(date_iso, km)

        if key not in data:

            return False, None

        return True, data[key]

    @staticmethod
    def put(profile: str, date_iso: str, km: float, phases: list | None) -> None:

        data = SharePhasesStore._load(profile)

        data[SharePhasesStore.key(date_iso, km)] = phases

        if len(data) > _MAX_ENTRIES:

            data = dict(sorted(data.items(), reverse=True)[:_MAX_ENTRIES])

        _STORAGE.mkdir(parents=True, exist_ok=True)

        SharePhasesStore._file(profile).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8",
        )
