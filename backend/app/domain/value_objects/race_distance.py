"""Distância de uma PROVA a partir do nome que o atleta deu. Mais estrito que o
`BuildTrainingGoal._parse_distance` (que pega o primeiro número de um texto
livre): aqui um ano no nome ("... 2027") nunca vira distância — só vale número
colado em km/k, "meia" ou "maratona". None quando não há pista (o app pergunta)."""

import re

HALF_MARATHON_KM = 21.0975
MARATHON_KM = 42.195

# 15 km · 15km · 10k · 21,1 km · 5 quilômetros
_NUMBER_KM = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:km|quil[oô]metros?|k)\b", re.IGNORECASE
)

_MIN_KM = 0.4
_MAX_KM = 500.0


def parse_race_distance(name: str | None) -> float | None:

    if not name:

        return None

    low = name.lower()

    if "meia" in low and "marat" in low:

        return HALF_MARATHON_KM

    match = _NUMBER_KM.search(name)

    if match:

        km = float(match.group(1).replace(",", "."))

        return km if _MIN_KM <= km <= _MAX_KM else None

    if "marat" in low:

        return MARATHON_KM

    if re.search(r"\bmeia\b", low):

        return HALF_MARATHON_KM

    return None
