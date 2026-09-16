"""Proposta PENDENTE de treino avulso: o coach montou a sessão e ESPERA o 'SIM'
do atleta antes de gravar no plano. Guarda a sessão inteira (dict), a data e o
texto do preview — um 'sim' grava, um 'não' descarta e NADA fica no app. Vale
por uma janela curta (a proposta é do treino que acabou de sair)."""

import json
import time
from datetime import date
from pathlib import Path

_STORAGE = (
    Path(__file__).resolve().parents[4] / "storage" / "one_off" / "proposal"
)

# a proposta expira: um "sim" muito depois não deve gravar sozinho
_TTL_SECONDS = 12 * 3600


class OneOffProposalStore:

    @staticmethod
    def _file(profile: str) -> Path:

        return _STORAGE / f"{profile}.json"

    @staticmethod
    def set_pending(
        profile: str,
        session: dict,
        on_date: date,
        message: str,
    ) -> None:

        _STORAGE.mkdir(parents=True, exist_ok=True)

        OneOffProposalStore._file(profile).write_text(
            json.dumps(
                {
                    "ts": time.time(),
                    "date": on_date.isoformat(),
                    "session": session,
                    "message": message,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def pending(profile: str) -> dict | None:
        """Proposta se ainda VÁLIDA (dentro do TTL), senão None. Devolve
        {date, session, message}."""

        file = OneOffProposalStore._file(profile)

        if not file.exists():

            return None

        try:

            data = json.loads(file.read_text(encoding="utf-8"))

            if (time.time() - data["ts"]) >= _TTL_SECONDS:

                return None

            date.fromisoformat(data["date"])  # valida

            if not isinstance(data.get("session"), dict):

                return None

            return data

        except (json.JSONDecodeError, KeyError, ValueError, OSError, TypeError):

            return None

    @staticmethod
    def clear(profile: str) -> None:

        file = OneOffProposalStore._file(profile)

        if file.exists():

            file.unlink()
