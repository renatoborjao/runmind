"""Estado do LOOP de cadência por atleta — storage/cadence_progress/{profile}.json.

O coach não fala de cadência uma vez e some, nem repete a cada corrida: ele
ACOMPANHA a evolução. Este store guarda o pouco que o loop precisa pra reagir ao
que a cadência está realmente fazendo (subiu? travou? bateu o alvo?):

- state: "watching" (acompanhando) | "closed" (bateu o alvo, encerrado pra sempre)
- baseline_spm: a mediana de cadência quando o loop engatou / último marco
- anchor_date: quando a baseline foi fixada (ou o último progresso) — timer do
  re-nudge de estagnação
- re_nudged: se o único re-cutução de "travou" já saiu (depois disso, silêncio
  sobre estagnação — orienta, não cobra)

Gitignored (dado de atleta). Espelha o PaceProgressStore."""

import json
from datetime import date
from pathlib import Path


class CadenceProgressStore:

    def __init__(self):

        self.storage = (
            Path(__file__).resolve().parents[3] / "storage" / "cadence_progress"
        )

        self.storage.mkdir(parents=True, exist_ok=True)

    def _file(self, profile: str) -> Path:

        return self.storage / f"{profile}.json"

    def load(self, profile: str) -> dict | None:

        file = self._file(profile)

        if not file.exists():

            return None

        try:

            return json.loads(file.read_text(encoding="utf-8"))

        except Exception:

            return None

    def save(
        self,
        profile: str,
        *,
        state: str,
        baseline_spm: int,
        anchor_date: date,
        re_nudged: bool,
    ) -> None:

        self._file(profile).write_text(
            json.dumps(
                {
                    "state": state,
                    "baseline_spm": baseline_spm,
                    "anchor_date": anchor_date.isoformat(),
                    "re_nudged": re_nudged,
                }
            ),
            encoding="utf-8",
        )
