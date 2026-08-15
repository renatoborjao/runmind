"""Check-ins de sensação do atleta — storage/checkins/{profile}.json.

Um por dia (colapsa: um novo relato no mesmo dia substitui/funde o anterior),
série ordenada, com teto. Gitignored (dado de atleta). Ver
[[project_ideias_produto]] item 4."""

import json
from dataclasses import asdict
from pathlib import Path

from app.domain.entities.daily_checkin import DailyCheckin

# quantos check-ins guardar (histórico curto basta; o valor é o estado recente)
_MAX = 60

# dor a partir da qual vale ACOMPANHAR depois (moderada pra cima; 1-2 é ruído)
_CONCERN_SORENESS = 3


class CheckinRepository:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "checkins"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def load(self, profile: str) -> list[DailyCheckin]:

        file = self.storage / f"{profile}.json"

        if not file.exists():

            return []

        with open(file, encoding="utf-8") as f:

            return [DailyCheckin(**record) for record in json.load(f)]

    def record(self, profile: str, checkin: DailyCheckin) -> None:
        """Grava o check-in. No MESMO dia, FUNDE com o existente — um segundo
        relato ('e a perna tá doendo') completa o primeiro em vez de apagá-lo."""

        checkins = self.load(profile)

        if checkins and checkins[-1].day == checkin.day:

            checkins[-1] = CheckinRepository._merge(checkins[-1], checkin)

        else:

            checkins.append(checkin)

        self._save(profile, checkins[-_MAX:])

    def latest_recent(
        self, profile: str, today: str, within_days: int = 2
    ) -> DailyCheckin | None:
        """O check-in mais recente dentro dos últimos `within_days` dias — o
        que ainda vale pra decisão de hoje. Estado antigo não conta (a sensação
        é transitória, não durável como a memória de vida)."""

        from datetime import date, timedelta

        checkins = self.load(profile)

        if not checkins:

            return None

        last = checkins[-1]

        try:

            cutoff = date.fromisoformat(today) - timedelta(days=within_days)

            if date.fromisoformat(last.day) < cutoff:

                return None

        except ValueError:

            return None

        return last if last.has_data else None

    def recent_concern(
        self, profile: str, today: str, within_days: int = 6
    ) -> DailyCheckin | None:
        """A QUEIXA mais recente (doença OU dor moderada+) nos últimos
        `within_days` — o que o coach deve ACOMPANHAR depois ("como está a
        gripe/dor?"). None se não há queixa recente."""

        from datetime import date, timedelta

        try:

            cutoff = date.fromisoformat(today) - timedelta(days=within_days)

        except ValueError:

            return None

        for checkin in reversed(self.load(profile)):

            is_concern = checkin.illness or (
                checkin.soreness is not None
                and checkin.soreness >= _CONCERN_SORENESS
            )

            if not is_concern:

                continue

            try:

                if date.fromisoformat(checkin.day) >= cutoff:

                    return checkin

            except ValueError:

                continue

        return None

    # ------------------------------------------------------------------

    @staticmethod
    def _merge(old: DailyCheckin, new: DailyCheckin) -> DailyCheckin:
        """Novo relato do mesmo dia preenche o que trouxe; o resto do antigo
        permanece. A nota mais recente vence (é a informação mais atual)."""

        return DailyCheckin(
            day=new.day,
            at=new.at,
            energy=new.energy if new.energy is not None else old.energy,
            sleep_quality=(
                new.sleep_quality
                if new.sleep_quality is not None
                else old.sleep_quality
            ),
            soreness=(
                new.soreness if new.soreness is not None else old.soreness
            ),
            # doença é sinal "pega ou não pega" — uma vez sinalizado no dia,
            # permanece (um segundo relato sem doença não apaga a gripe)
            illness=new.illness or old.illness,
            note=new.note or old.note,
        )

    def recent_illness(
        self, profile: str, today: str, within_days: int = 4
    ) -> DailyCheckin | None:
        """O relato de DOENÇA mais recente dentro dos últimos `within_days` —
        janela maior que a do estado geral (gripe/resfriado dura dias). None se
        não há doença recente. É o que segura o 'pode puxar' de um atleta que
        avisou que está doente."""

        from datetime import date, timedelta

        try:

            cutoff = date.fromisoformat(today) - timedelta(days=within_days)

        except ValueError:

            return None

        for checkin in reversed(self.load(profile)):

            if not checkin.illness:

                continue

            try:

                if date.fromisoformat(checkin.day) >= cutoff:

                    return checkin

            except ValueError:

                continue

        return None

    def _save(self, profile: str, checkins: list[DailyCheckin]) -> None:

        file = self.storage / f"{profile}.json"

        with open(file, "w", encoding="utf-8") as f:

            json.dump(
                [asdict(c) for c in checkins],
                f,
                ensure_ascii=False,
                indent=2,
            )
