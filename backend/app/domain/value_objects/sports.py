# O RunMind só trata treinos a pé: corrida, caminhada e esteira.
# Esteira no Strava chega como "Run" (com trainer=true) ou "VirtualRun".
# Qualquer outro esporte (Ride, Swim, WeightTraining...) polui os
# agregadores semanais e a comparação com o plano.

FOOT_SPORTS = {
    "Run",
    "TrailRun",
    "VirtualRun",
    "Walk",
    "Hike",
}


def is_foot_sport(sport: str) -> bool:

    return sport in FOOT_SPORTS


# Subconjunto de FOOT_SPORTS que conta como CORRIDA de verdade — usado onde
# caminhada/hike não deve competir (recorde de corrida, previsão de prova).
RUN_SPORTS = {
    "Run",
    "TrailRun",
    "VirtualRun",
}


def is_run_sport(sport: str) -> bool:

    return sport in RUN_SPORTS
