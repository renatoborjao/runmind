from app.application.rules.distance_rule import DistanceRule
from app.application.rules.heart_rate_rule import HeartRateRule
from app.application.rules.pace_rule import PaceRule
from app.domain.entities.activity import Activity


class RulesEngine:

    @staticmethod
    def analyze(activity: Activity):

        score = 80

        positives = []
        attention = []
        recommendations = []

        rules = [
            PaceRule.execute(activity),
            HeartRateRule.execute(activity),
            DistanceRule.execute(activity),
        ]

        for result in rules:

            score += result.get("score", 0)

            positives.extend(
                result.get("positives", [])
            )

            attention.extend(
                result.get("attention", [])
            )

            recommendations.extend(
                result.get("recommendations", [])
            )

        if score >= 90:
            status = "Excelente"
        elif score >= 80:
            status = "Bom"
        elif score >= 70:
            status = "Regular"
        else:
            status = "Ruim"

        return {
            "score": score,
            "status": status,
            "positives": positives,
            "attention": attention,
            "recommendations": recommendations,
        }