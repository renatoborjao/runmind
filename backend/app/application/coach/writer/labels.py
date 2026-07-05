# Vocabulário de exibição em pt-BR. Os códigos internos (enums) nunca
# devem aparecer crus em mensagem ao corredor.

WORKOUT_TYPE_LABELS = {
    "RECOVERY": "Regenerativo",
    "EASY": "Rodagem leve",
    "RODAGEM": "Rodagem",
    "TEMPO": "Ritmo",
    "PROGRESSION": "Progressivo",
    "VO2": "Intervalado",
    "FARTLEK": "Fartlek",
    "LONG_RUN": "Longão",
    "WALK": "Caminhada",
    "RUN_WALK": "Corrida-caminhada",
    "UNKNOWN": "—",
}

# Abaixo disso, a sessão mais longa não é "longão" de verdade.
LONG_RUN_LABEL_MIN_KM = 10.0

INTENSITY_LABELS = {
    "VERY_HIGH": "Muito alta",
    "HIGH": "Alta",
    "MEDIUM": "Moderada",
    "LOW": "Leve",
    "VERY_LOW": "Muito leve",
}


def workout_type_label(training_type: str) -> str:

    return WORKOUT_TYPE_LABELS.get(training_type, training_type)


def plan_workout_label(
    code: str,
    distance_km: float | None = None,
) -> str:
    """Rótulo do treino planejado. O longão só se chama "Longão" quando
    é de fato longo; curto vira "Rodagem longa"."""

    if code == "LONG_RUN":

        if distance_km is not None and distance_km < LONG_RUN_LABEL_MIN_KM:

            return "Rodagem longa"

        return "Longão"

    return workout_type_label(code)


def intensity_label(intensity: str) -> str:

    return INTENSITY_LABELS.get(intensity, intensity)
