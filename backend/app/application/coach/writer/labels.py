# Vocabulário de exibição em pt-BR. Os códigos internos (enums) nunca
# devem aparecer crus em mensagem ao corredor.

WORKOUT_TYPE_LABELS = {
    "RECOVERY": "Regenerativo",
    "EASY": "Rodagem leve",
    "RODAGEM": "Rodagem",
    "TEMPO": "Ritmo",
    "THRESHOLD": "Limiar",
    "PROGRESSION": "Progressivo",
    "VO2": "Intervalado",
    "INTERVAL": "Intervalado",
    "FARTLEK": "Fartlek",
    "LONG_RUN": "Longão",
    "RACE": "Prova",
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


def plan_session_title(session, executed_km: float | None = None) -> str:
    """Título do treino como vai pro RELÓGIO (Garmin) e pro STRAVA — uma fonte
    só, sem drift. Ex.: 'Ritmind · Longão Aeróbico 13.0km' / 'Ritmind ·
    Rodagem por Tempo'. Reusado por garmin_push e pelo renomeador do Strava.

    `executed_km` (só o Strava passa, PÓS-corrida): se o atleta correu MENOS
    que o planejado (na casa decimal do título), o nome sai SEM distância
    ('Longão Progressivo') — nunca '14.5km' numa corrida de 13.5; o km real o
    Strava já mostra. Correu igual ou mais → mantém o planejado
    (o título é o do treino, não o do excedente). Sem `executed_km` (relógio,
    PRÉ-corrida) o alvo planejado é o certo."""

    label = plan_workout_label(
        getattr(session, "workout_type", "") or "",
        getattr(session, "planned_distance_km", None),
    )

    km = getattr(session, "planned_distance_km", None)

    if not km:

        return f"Ritmind · {label}"

    # compara na mesma precisão do título (0.1 km): 14.46 de 14.5 é "14.5"
    if executed_km and round(executed_km, 1) < round(km, 1):

        return f"Ritmind · {label}"

    return f"Ritmind · {label} {km:.1f}km"


def intensity_label(intensity: str) -> str:

    return INTENSITY_LABELS.get(intensity, intensity)
