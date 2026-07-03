# Vocabulário de exibição em pt-BR. Os códigos internos (enums) nunca
# devem aparecer crus em mensagem ao corredor.

WORKOUT_TYPE_LABELS = {
    "RECOVERY": "Regenerativo",
    "EASY": "Rodagem leve",
    "TEMPO": "Tempo run",
    "VO2": "Intervalado (VO2)",
    "LONG_RUN": "Longão",
    "UNKNOWN": "—",
}

INTENSITY_LABELS = {
    "VERY_HIGH": "Muito alta",
    "HIGH": "Alta",
    "MEDIUM": "Moderada",
    "LOW": "Leve",
    "VERY_LOW": "Muito leve",
}


def workout_type_label(training_type: str) -> str:

    return WORKOUT_TYPE_LABELS.get(training_type, training_type)


def intensity_label(intensity: str) -> str:

    return INTENSITY_LABELS.get(intensity, intensity)
