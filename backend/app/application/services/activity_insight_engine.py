from __future__ import annotations

from app.domain.entities.activity import Activity


class ActivityInsightEngine:
    """
    Gera positives/attention/recommendations para o relatório de atividade.

    No futuro receberá também o histórico de treinos,
    perfil do atleta e objetivo.
    """

    @staticmethod
    def analyze(activity: Activity) -> dict:

        positives = []
        attention = []
        recommendations = []

        # Frequência cardíaca
        if activity.average_heartrate:

            if activity.average_heartrate < 150:
                positives.append(
                    "Boa eficiência cardiovascular durante o treino."
                )

            elif activity.average_heartrate > 175:
                attention.append(
                    "Frequência cardíaca média bastante elevada."
                )

        # Distância
        if activity.distance >= 10000:
            positives.append(
                "Excelente volume para desenvolvimento da resistência."
            )

        elif activity.distance < 5000:
            attention.append(
                "Treino curto. Avaliar se estava previsto."
            )

        # Altimetria
        if activity.elevation_gain > 100:
            positives.append(
                "Treino com boa carga de subida."
            )

        recommendations.append(
            "Analisar os últimos treinos para identificar evolução."
        )

        return {
            "score": 8.5,
            "positives": positives,
            "attention": attention,
            "recommendations": recommendations,
        }
