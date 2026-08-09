import json
from pathlib import Path

_STORAGE = Path(__file__).resolve().parents[3] / "storage"


class CoachBrainHealthRepository:
    """Estado do monitor de SAÚDE do cérebro do coach: janela rolante dos
    últimos desfechos (1 = caiu no fallback / cérebro devolveu None; 0 = o
    cérebro respondeu) + flag de 'já alertou'. Persistido pra sobreviver a
    restart.

    storage/coach_brain_health.json — {"window": [0/1,...], "alerted": bool}.
    """

    def __init__(self):

        _STORAGE.mkdir(parents=True, exist_ok=True)

        self.file = _STORAGE / "coach_brain_health.json"

    def load(self) -> dict:

        if not self.file.exists():

            return {"window": [], "alerted": False}

        try:

            with open(self.file, encoding="utf-8") as f:

                return json.load(f)

        except (json.JSONDecodeError, OSError, TypeError):

            return {"window": [], "alerted": False}

    def save(self, state: dict) -> None:

        with open(self.file, "w", encoding="utf-8") as f:

            json.dump(state, f)
