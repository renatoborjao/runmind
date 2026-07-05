from statistics import median


class PlanBaselineBuilder:
    """Transforma as sessões de um plano importado (extraídas por visão do
    Gemini, mesmo motor do modo treinador) no retrato-base do atleta:
    volume, frequência, rodagem típica e maior treino. Vira o PISO do
    baseline quando o histórico do Strava é fino."""

    @staticmethod
    def from_sessions(sessions: list[dict]) -> dict | None:

        distances = [
            float(session["distance_km"])
            for session in sessions
            if isinstance(session.get("distance_km"), (int, float))
            and session["distance_km"] > 0
        ]

        # sem corridas com distância (só musculação/tempo?) não dá retrato
        if not distances:

            return None

        return {
            "weekly_km": round(sum(distances), 1),
            "runs_per_week": len(distances),
            "typical_km": round(median(distances), 1),
            "longest_km": round(max(distances), 1),
        }
