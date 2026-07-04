import re
import unicodedata
from dataclasses import dataclass

# dia em pt-BR (sem acento) -> nome interno
_WEEKDAYS_PT = {
    "segunda": "Monday",
    "terca": "Tuesday",
    "quarta": "Wednesday",
    "quinta": "Thursday",
    "sexta": "Friday",
    "sabado": "Saturday",
    "domingo": "Sunday",
}

# Só dispara com uma intenção clara de definir/manter (evita perguntas
# como "como foi meu longão de domingo?", que não têm esses termos).
_CUES = [
    "gosto", "prefiro", "prefere", "quero", "gostaria", "curto",
    "pode ser", "poderia", "mantem", "manter", "mantenha", "mantém",
    "deixa", "deixar", "coloca", "colocar", "bota", "botar", "poe",
    "poem", "faco", "faço", "sempre", "costumo", "muda", "mudar",
    "troca", "trocar", "passa", "passar",
]


@dataclass(slots=True)
class PlanPreference:

    long_run_day: str


class PlanPreferenceDetector:
    """Detecta, de forma determinística, o pedido do atleta de fixar o
    longão num dia ("domingo eu gosto de longão, pode manter"). v1 cobre
    só o dia do longão — o pedido mais concreto do Renato."""

    @staticmethod
    def detect(text: str) -> PlanPreference | None:

        norm = PlanPreferenceDetector._normalize(text)

        mentions_long = "longao" in norm or "long run" in norm

        if not mentions_long:

            return None

        if not any(cue in norm for cue in _CUES):

            return None

        for pt_day, internal in _WEEKDAYS_PT.items():

            if re.search(rf"\b{pt_day}\b", norm):

                return PlanPreference(long_run_day=internal)

        return None

    @staticmethod
    def _normalize(text: str) -> str:

        lowered = text.lower().strip()

        without_accents = "".join(
            char
            for char in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(char) != "Mn"
        )

        return re.sub(r"\s+", " ", without_accents)
