"""Fluxo do sRPE: o coach pergunta o RPE após o treino e captura a resposta.

- `ask_line()`: a pergunta anexada ao feedback ("de 0 a 10, quão puxado foi?").
- `resolve()`: quando há um treino PENDENTE de RPE e o atleta responde um
  número 0-10, grava o sRPE (duração × RPE) e agradece. Só interpreta número
  solto como RPE quando há pendente recente — senão devolve None e a conversa
  segue normal (evita ler "corri 8km" como RPE 8). Ver [[project_ideias_produto]]."""

import re
import unicodedata
from datetime import date, timedelta

from app.core.clock import now_local, today_local
from app.domain.entities.session_rpe import SessionRpe
from app.infrastructure.persistence.session_rpe_repository import (
    SessionRpeRepository,
)

# unidades que denunciam que o número NÃO é RPE (distância, pace, tempo)
_UNIT_HINTS = ("km", "quilomet", "metro", "min", "kmh", "km/h", "pace", ":")

_LABELED = re.compile(
    r"\b(?:rpe|nota|esforco|nivel|foi|uns?|deu)\s*(\d{1,2})\b"
)

_OUT_OF_TEN = re.compile(r"\b(\d{1,2})\s*(?:/|de)\s*10\b")

_BARE = re.compile(r"^\s*(\d{1,2})\s*$")


class RpeFlow:

    ASK_LINE = (
        "💬 De 0 a 10, quão puxado foi esse treino? "
        "(só o número — eu uso pra calibrar sua carga)"
    )

    @staticmethod
    def resolve(profile: str, incoming_text: str) -> str | None:

        repo = SessionRpeRepository()

        pending = repo.get_pending(profile)

        if not pending:

            return None

        # pendente velho (atleta não respondeu no dia): não captura número
        # solto dias depois como se fosse o RPE daquele treino
        if RpeFlow._is_stale(pending.get("day")):

            repo.clear_pending(profile)

            return None

        rpe = RpeFlow._parse_rpe(incoming_text)

        if rpe is None:

            return None

        duration_min = float(pending.get("duration_min") or 0)

        srpe = round(duration_min * rpe, 1)

        repo.record(
            profile,
            SessionRpe(
                activity_id=int(pending["activity_id"]),
                day=pending["day"],
                duration_min=round(duration_min, 1),
                rpe=rpe,
                srpe=srpe,
                at=now_local().isoformat(),
            ),
        )

        return RpeFlow._ack(rpe)

    @staticmethod
    def recent_note(profile: str) -> str:
        """Sinal de dose quando o ÚLTIMO treino foi percebido como muito puxado
        (RPE alto e recente): mesmo que o Garmin não tenha achado pesado, a
        percepção conta. String vazia caso contrário (nada a injetar)."""

        latest = SessionRpeRepository().latest(profile)

        if latest is None or latest.rpe < 8:

            return ""

        try:

            recent = (
                date.fromisoformat(latest.day)
                >= today_local() - timedelta(days=3)
            )

        except ValueError:

            return ""

        if not recent:

            return ""

        return (
            f"O atleta PERCEBEU o último treino como muito puxado "
            f"(RPE {latest.rpe}/10) — considere na dose, mesmo que os números "
            f"do relógio não mostrem sobrecarga."
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _ack(rpe: int) -> str:

        if rpe >= 8:

            tone = "puxado mesmo — vou considerar isso na sua recuperação e na dose. 💪"

        elif rpe <= 3:

            tone = "tranquilo então — bom sinal de que a carga tá bem absorvida. 👊"

        else:

            tone = "anotado — carga na medida. 👊"

        return f"Valeu! RPE {rpe}/10, {tone}"

    @staticmethod
    def _is_stale(day: str | None) -> bool:
        """Pendente vale só até o dia seguinte ao treino."""

        if not day:

            return True

        try:

            return date.fromisoformat(day) < today_local() - timedelta(days=1)

        except ValueError:

            return True

    @staticmethod
    def _parse_rpe(text: str) -> int | None:
        """Extrai um RPE 0-10 de uma resposta curta. None se não parecer RPE
        (mensagem com km/pace/tempo, ou sem número claro)."""

        normalized = RpeFlow._normalize(text)

        if any(hint in normalized for hint in _UNIT_HINTS):

            return None

        for pattern in (_BARE, _OUT_OF_TEN, _LABELED):

            match = pattern.search(normalized)

            if match:

                value = int(match.group(1))

                if 0 <= value <= 10:

                    return value

        return None

    @staticmethod
    def _normalize(text: str) -> str:

        lowered = text.lower().strip()

        return "".join(
            c
            for c in unicodedata.normalize("NFD", lowered)
            if unicodedata.category(c) != "Mn"
        )
