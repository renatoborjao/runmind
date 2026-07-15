"""Dedup dos disparos agendados no MULTI-FUSO. Como os jobs agora rodam de
hora em hora (pra enviar no horário LOCAL de cada atleta), este guard garante
que cada atleta receba a mensagem UMA vez por período: por DIA (briefing,
lembrete externo) ou por SEMANA (plano de domingo, review). `period_key` é a
data local (diário) ou a semana ISO local (semanal)."""

import json
from pathlib import Path

_STORAGE = Path(__file__).resolve().parents[3] / "storage" / "dispatch_log"


class DispatchGuard:

    @staticmethod
    def _file(kind: str) -> Path:

        return _STORAGE / f"{kind}.json"

    @staticmethod
    def _load(kind: str) -> dict:

        file = DispatchGuard._file(kind)

        if not file.exists():

            return {}

        try:

            return json.loads(file.read_text(encoding="utf-8"))

        except (json.JSONDecodeError, OSError):

            return {}

    @staticmethod
    def already_sent(kind: str, profile: str, period_key: str) -> bool:

        return DispatchGuard._load(kind).get(profile) == period_key

    @staticmethod
    def mark(kind: str, profile: str, period_key: str) -> None:

        _STORAGE.mkdir(parents=True, exist_ok=True)

        data = DispatchGuard._load(kind)

        data[profile] = period_key

        DispatchGuard._file(kind).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
