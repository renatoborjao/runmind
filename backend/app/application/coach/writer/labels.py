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


# quanto a corrida pode ficar ABAIXO do planejado e ainda levar o km no nome
_SHORT_TOLERANCE_KM = 0.5


def plan_session_title(session, executed_km: float | None = None) -> str:
    """Título do treino como vai pro RELÓGIO (Garmin) e pro STRAVA — uma fonte
    só, sem drift. Ex.: 'Ritmind · Longão Aeróbico 13.0km' / 'Ritmind ·
    Rodagem por Tempo'. Reusado por garmin_push e pelo renomeador do Strava.

    `executed_km` (só o Strava passa, PÓS-corrida): o km só fica no nome se a
    corrida ficou na JANELA do planejado — de 0,5 km a menos até o fim do km
    inteiro dele: planejado 12, correu de 11.5 a 12.9 → 'Longão 12.0km'.
    Correu mais de 0,5 km a menos (nunca '14.5km' numa de 13.5) ou passou pro
    km seguinte (13.0+ num de 12) → sai SEM distância ('Longão Progressivo');
    o km real o Strava já mostra. Sem `executed_km` (relógio, PRÉ-corrida) o
    alvo planejado é o certo."""

    label = plan_workout_label(
        getattr(session, "workout_type", "") or "",
        getattr(session, "planned_distance_km", None),
    )

    km = getattr(session, "planned_distance_km", None)

    if not km:

        return f"Ritmind · {label}"

    if executed_km:

        # ficou a mais de 0,5 km do planejado (11.5 de 12 ainda é "12"),
        # comparado na precisão do título (0.1 km)
        fell_short = round(executed_km, 1) < round(km - _SHORT_TOLERANCE_KM, 1)

        # estourou o km inteiro do planejado: 12.9 num de 12 ainda é "12";
        # 13.0 já não
        overshot = executed_km >= int(round(km, 1)) + 1

        if fell_short or overshot:

            return f"Ritmind · {label}"

    return f"Ritmind · {label} {km:.1f}km"


def intensity_label(intensity: str) -> str:

    return INTENSITY_LABELS.get(intensity, intensity)
