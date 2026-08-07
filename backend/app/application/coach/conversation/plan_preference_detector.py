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


__all__ = ["PlanPreference", "PlanPreferenceDetector"]


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

        # MOVE de uma sessão específica NÃO é preferência durável de dia — deixa
        # o MoveSkipFlow cuidar (cirúrgico + relógio). Sem isto, "mudar meu
        # treino DE domingo PARA amanhã" pescava "domingo" (o dia de ORIGEM) e
        # respondia "quer incluir domingo nos seus dias?" — o oposto do pedido
        # (bug recorrente do Renato). Move se tem alvo relativo (amanhã/hoje) ou
        # origem→destino entre dois dias diferentes ("de sábado pra domingo").
        if PlanPreferenceDetector._looks_like_move(norm):

            return None

        for pt_day, internal in _WEEKDAYS_PT.items():

            if re.search(rf"\b{pt_day}\b", norm):

                return PlanPreference(long_run_day=internal)

        return None

    # alvos relativos de UMA ocorrência — nunca são preferência durável de dia
    _RELATIVE_TARGETS = (
        "para amanha", "pra amanha", "para hoje", "pra hoje",
        "para depois de amanha", "pra depois de amanha",
    )

    @staticmethod
    def _looks_like_move(norm: str) -> bool:
        """True quando a frase move UMA sessão (não fixa um dia de longão):
        alvo relativo (amanhã/hoje) OU origem→destino entre dias diferentes."""

        if any(target in norm for target in PlanPreferenceDetector._RELATIVE_TARGETS):

            return True

        days = "|".join(_WEEKDAYS_PT)  # segunda|terca|...|domingo

        match = re.search(
            rf"\bde ({days})\b.*\b(?:para|pra) ({days})\b",
            norm,
        )

        return bool(match) and match.group(1) != match.group(2)

    @staticmethod
    def _normalize(text: str) -> str:

        lowered = text.lower().strip()

        without_accents = "".join(
            char
            for char in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(char) != "Mn"
        )

        return re.sub(r"\s+", " ", without_accents)
