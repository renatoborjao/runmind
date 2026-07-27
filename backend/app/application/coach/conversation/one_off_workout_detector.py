import re
import unicodedata
from datetime import date, timedelta

# portão determinístico BARATO: só chama a IA se a mensagem cheira a pedido pra
# MONTAR um treino avulso ("monta um treino pra domingo", "que treino faço
# amanhã?"). Falso positivo aqui não custa quase nada (o fluxo só age se achar
# uma data e um atleta elegível).
_BUILD_VERBS = [
    "monta", "montar", "monte", "me monta", "bola", "bolar", "cria",
    "criar", "sugere", "sugerir", "prepara", "preparar", "manda um treino",
    "me passa um treino", "passa um treino", "faz um treino", "faz o treino",
    "fazer um treino", "que treino", "qual treino", "que treino faco",
]

# dia da semana em pt-BR (sem acento) -> índice weekday() (0=segunda)
_WEEKDAYS_PT = {
    "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3,
    "sexta": 4, "sabado": 5, "domingo": 6,
}

# mês por extenso -> número (pra "dia 1 de agosto")
_MONTHS_PT = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}


class OneOffWorkoutDetector:
    """Detecta o pedido de montar um treino avulso e resolve a data alvo a
    partir de texto livre ('domingo', 'amanhã', '01/08', 'dia 1')."""

    @staticmethod
    def looks_like_request(text: str) -> bool:

        norm = OneOffWorkoutDetector._normalize(text)

        has_treino = "treino" in norm or "treininho" in norm

        has_build = any(verb in norm for verb in _BUILD_VERBS)

        return has_treino and has_build

    @staticmethod
    def resolve_target_date(text: str, today: date) -> date | None:
        """Data concreta pedida na mensagem, ou None se não deu pra saber.
        Dia da semana resolve pra a PRÓXIMA ocorrência (hoje conta)."""

        norm = OneOffWorkoutDetector._normalize(text)

        # relativos primeiro (mais específicos que um número solto)
        if "depois de amanha" in norm:

            return today + timedelta(days=2)

        if "amanha" in norm:

            return today + timedelta(days=1)

        if "hoje" in norm:

            return today

        # dd/mm ou dd-mm
        match = re.search(r"\b(\d{1,2})[/-](\d{1,2})\b", norm)

        if match:

            return OneOffWorkoutDetector._safe_date(
                today, int(match.group(2)), int(match.group(1))
            )

        # "dia 1 de agosto" / "dia 1"
        match = re.search(r"\bdia (\d{1,2})\b", norm)

        if match:

            day = int(match.group(1))

            month = today.month

            for name, number in _MONTHS_PT.items():

                if name in norm:

                    month = number

                    break

            return OneOffWorkoutDetector._safe_date(today, month, day)

        # dia da semana por nome -> próxima ocorrência (hoje inclusive)
        for name, weekday in _WEEKDAYS_PT.items():

            if re.search(rf"\b{name}\b", norm):

                days_ahead = (weekday - today.weekday()) % 7

                return today + timedelta(days=days_ahead)

        return None

    @staticmethod
    def _safe_date(today: date, month: int, day: int) -> date | None:
        """Monta a data no ano corrente; se já passou (mais de uma semana
        atrás), joga pro ano seguinte. Data inválida -> None."""

        for year in (today.year, today.year + 1):

            try:

                candidate = date(year, month, day)

            except ValueError:

                return None

            if candidate >= today - timedelta(days=7):

                return candidate

        return None

    @staticmethod
    def _normalize(text: str) -> str:

        lowered = (text or "").lower().strip()

        without_accents = "".join(
            char
            for char in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(char) != "Mn"
        )

        return re.sub(r"\s+", " ", without_accents)
