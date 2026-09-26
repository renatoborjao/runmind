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

# o "pra qual dia?" é pergunta de conversa corrente, não de horas depois
_AWAITING_TTL_SECONDS = 30 * 60


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

    # --- pedido esperando o DIA ------------------------------------------
    # O coach perguntou "pra qual dia?": guarda o pedido original ("8km com
    # progressão") pra a resposta curta ("amanhã") não chegar sozinha no motor
    # e virar um treino que ignora o que o atleta pediu.

    @staticmethod
    def _awaiting_file(profile: str) -> Path:

        return _STORAGE / f"{profile}.awaiting.json"

    @staticmethod
    def set_awaiting_day(profile: str, request: str) -> None:

        _STORAGE.mkdir(parents=True, exist_ok=True)

        OneOffProposalStore._awaiting_file(profile).write_text(
            json.dumps(
                {"ts": time.time(), "request": request}, ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def pop_awaiting_day(profile: str) -> str | None:
        """Pedido que ficou esperando o dia (se recente) — e limpa."""

        file = OneOffProposalStore._awaiting_file(profile)

        if not file.exists():

            return None

        try:

            data = json.loads(file.read_text(encoding="utf-8"))

            file.unlink()

            if (time.time() - data["ts"]) >= _AWAITING_TTL_SECONDS:

                return None

            return str(data["request"]).strip() or None

        except (json.JSONDecodeError, KeyError, OSError, TypeError):

            return None
