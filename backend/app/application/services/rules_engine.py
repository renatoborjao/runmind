from app.domain.entities.activity import Activity


class RulesEngine:

    @staticmethod
    def analyze(activity: Activity):

        positives = []
        attention = []
        recommendations = []

        score = 80

        pace = activity.average_speed * 3.6

        if pace >= 10:

            positives.append(
                "Excelente velocidade média."
            )

            score += 5

        else:

            attention.append(
                "Velocidade abaixo de 10 km/h."
            )

        if activity.average_heartrate:

            if activity.average_heartrate <= 160:

                positives.append(
                    "Boa eficiência cardíaca."
                )

                score += 5

            else:

                attention.append(
                    "Frequência cardíaca elevada."
                )

        if activity.distance >= 10000:

            positives.append(
                "Bom volume de treino."
            )

            score += 5

        else:

            recommendations.append(
                "Aumentar gradualmente o volume semanal."
            )

        status = "Excelente"

        if score < 70:
            status = "Ruim"

        elif score < 80:
            status = "Regular"

        elif score < 90:
            status = "Bom"

        return {

            "score": score,

            "status": status,

            "positives": positives,

            "attention": attention,

            "recommendations": recommendations,

        }