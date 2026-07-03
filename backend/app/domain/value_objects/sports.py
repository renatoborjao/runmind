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
