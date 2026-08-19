"""Diário do coach: registra TODA mensagem PROATIVA enviada (o que o coach
INICIOU), por atleta — a fonte única de "o que já foi dito hoje". Distinto do
`coach_outbox` (que guarda o TEXTO pro coach lembrar no chat): aqui guardamos os
METADADOS de política (tipo, tier, dia local, hash) pro governador decidir
orçamento/dedup e pra observabilidade (/debug/proactive/{profile}).

storage/proactive_ledger/{profile}.json (lista curta, mais recentes no fim).
Gitignored."""

import json
from datetime import UTC, datetime
from pathlib import Path

# quantas entradas guardar por atleta (alguns dias de histórico bastam pro
# orçamento do dia + observabilidade; não é arquivo de auditoria eterno)
_MAX_ENTRIES = 40


class ProactiveLedgerRepository:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "proactive_ledger"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def _load(self, profile: str) -> list[dict]:

        file = self._file(profile)

        if not file.exists():

            return []

        try:

            return json.loads(file.read_text(encoding="utf-8"))

        except (json.JSONDecodeError, OSError):

            return []

    def today(self, profile: str, day_iso: str) -> list[dict]:
        """As entradas enviadas no DIA LOCAL `day_iso` (o chamador passa o dia
        no fuso do atleta)."""

        return [e for e in self._load(profile) if e.get("day") == day_iso]

    def append(
        self, profile: str, kind: str, tier: int, day_iso: str, content_hash: str,
    ) -> None:

        entries = self._load(profile)

        entries.append(
            {
                "kind": kind,
                "tier": tier,
                "day": day_iso,
                "hash": content_hash,
                "ts": datetime.now(UTC).isoformat(),
            }
        )

        entries = entries[-_MAX_ENTRIES:]

        self._file(profile).write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def recent(self, profile: str, limit: int = 15) -> list[dict]:

        return self._load(profile)[-limit:]
