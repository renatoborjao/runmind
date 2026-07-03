from app.application.coach.signals.codes import (
    ConsistencyLevel,
    DistanceStatus,
    FatigueLevel,
    InjuryStatus,
    IntensityLevel,
    PaceEffortLevel,
    RecoveryStatus,
    TypeMatchStatus,
    WeeklyVolumeStatus,
    WorkoutPlanStatus,
)

# Todas as frases abaixo sao copiadas literalmente do que ja existia
# espalhado em coach/coach_engine.py, intelligence/*.py e analyzer/*.py.
# Nenhuma frase nova foi inventada nesta migracao.

GREETING_TEMPLATE = "Parabéns pelo treino, {name}! 👊"

DISTANCE_TEMPLATES = {
    DistanceStatus.OK.value: (
        "Você executou praticamente a mesma distância planejada."
    ),
    DistanceStatus.ABOVE.value: (
        "Hoje você correu {delta_percent:.0f}% acima da distância "
        "prevista. Esse aumento gera uma carga maior para o organismo."
    ),
    DistanceStatus.BELOW.value: (
        "Você ficou {delta_percent_abs:.0f}% abaixo da distância "
        "planejada. Tudo bem acontecer ocasionalmente — o importante "
        "é manter a consistência."
    ),
    DistanceStatus.UNKNOWN.value: None,
}

WORKOUT_PLAN_TEMPLATES = {
    WorkoutPlanStatus.UNPLANNED.value: (
        "Hoje não era um dia planejado de corrida — registrei como "
        "treino extra. Fique de olho na carga total da semana."
    ),
}

TYPE_MATCH_TEMPLATES = {
    TypeMatchStatus.MATCH.value: (
        "Você respeitou bem o objetivo principal da sessão."
    ),
    TypeMatchStatus.MISMATCH.value: (
        "O objetivo era um treino de {planned_type}, mas sua execução "
        "ficou mais próxima de um treino {executed_type}. Cada sessão "
        "possui um objetivo específico dentro do plano."
    ),
}

INTENSITY_TEMPLATES = {
    IntensityLevel.VERY_HIGH.value: (
        "O esforço foi muito elevado. Priorize descanso e hidratação."
    ),
    IntensityLevel.HIGH.value: (
        "Foi um treino intenso e com excelente estímulo cardiovascular."
    ),
    IntensityLevel.MEDIUM.value: (
        "Intensidade adequada para gerar evolução com segurança."
    ),
    IntensityLevel.LOW.value: (
        "Rodagem leve, ótima para recuperação e construção de base."
    ),
}

PACE_EFFORT_TEMPLATES = {
    PaceEffortLevel.VERY_FAST.value: (
        "Hoje você apresentou um ritmo muito elevado."
    ),
    PaceEffortLevel.FAST.value: (
        "Seu ritmo ficou dentro de uma intensidade forte."
    ),
    PaceEffortLevel.MODERATE.value: (
        "Foi uma rodagem confortável."
    ),
    PaceEffortLevel.EASY.value: (
        "Sessão predominantemente regenerativa."
    ),
}

RECOVERY_TEMPLATES = {
    RecoveryStatus.LONG.value: (
        "Evite sessões intensas antes da recuperação completa."
    ),
    RecoveryStatus.MODERATE.value: (
        "Priorize recuperação ativa amanhã."
    ),
    RecoveryStatus.SHORT.value: (
        "Seu organismo respondeu bem ao estímulo."
    ),
}

FATIGUE_TEMPLATES = {
    FatigueLevel.HIGH.value: (
        "Sua carga está bastante elevada. Observe sinais de fadiga."
    ),
    FatigueLevel.MODERATE.value: (
        "A carga foi significativa, mas dentro do esperado."
    ),
}

CONSISTENCY_TEMPLATES = {
    ConsistencyLevel.EXCELLENT.value: (
        "Excelente consistência nas últimas semanas."
    ),
    ConsistencyLevel.GOOD.value: (
        "Boa consistência de treinos."
    ),
    ConsistencyLevel.FAIR.value: (
        "A consistência pode melhorar."
    ),
    ConsistencyLevel.LOW.value: (
        "Sua rotina ainda está irregular."
    ),
}

INJURY_TEMPLATES = {
    InjuryStatus.ACTIVE.value: (
        "Você tem histórico de lesão registrado ({injuries}). "
        "Fique atento a qualquer desconforto e priorize a recuperação."
    ),
}

WEEKLY_VOLUME_TEMPLATES = {
    WeeklyVolumeStatus.COMPLETED.value: (
        "Todo o volume semanal já foi concluído."
    ),
    WeeklyVolumeStatus.NEAR_COMPLETE.value: (
        "Você está próximo de concluir o volume semanal."
    ),
    WeeklyVolumeStatus.IN_PROGRESS.value: None,
    WeeklyVolumeStatus.NO_GOAL.value: None,
}

ALL_TEMPLATES: dict[str, str | None] = {
    **DISTANCE_TEMPLATES,
    **WORKOUT_PLAN_TEMPLATES,
    **TYPE_MATCH_TEMPLATES,
    **INTENSITY_TEMPLATES,
    **PACE_EFFORT_TEMPLATES,
    **RECOVERY_TEMPLATES,
    **FATIGUE_TEMPLATES,
    **INJURY_TEMPLATES,
    **CONSISTENCY_TEMPLATES,
    **WEEKLY_VOLUME_TEMPLATES,
}

# Reproduz literalmente o "next_action" do antigo coach/coach_engine.py.
CLOSING_TEMPLATES = {
    RecoveryStatus.LONG.value: (
        "Evite treinos intensos até recuperar totalmente."
    ),
    RecoveryStatus.MODERATE.value: (
        "Se amanhã ainda houver fadiga, prefira uma rodagem leve."
    ),
    RecoveryStatus.SHORT.value: (
        "Você pode seguir normalmente com o planejamento."
    ),
}
