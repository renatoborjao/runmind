from app.domain.entities.activity import Activity


class DistanceRule:

    @staticmethod
    def execute(activity: Activity):

        positives = []
        recommendations = []
        score = 0

        if activity.distance >= 10000:

            positives.append("Bom volume de treino.")
            score += 5

        else:

            recommendations.append(
                "Aumentar gradualmente o volume semanal."
            )

        return {
            "score": score,
            "positives": positives,
            "recommendations": recommendations,
        }