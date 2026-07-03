from app.domain.entities.activity import Activity


class HeartRateRule:

    @staticmethod
    def execute(activity: Activity):

        positives = []
        attention = []
        score = 0

        if activity.average_heartrate:

            if activity.average_heartrate <= 160:

                positives.append("Boa eficiência cardíaca.")
                score += 5

            else:

                attention.append("Frequência cardíaca elevada.")

        return {
            "score": score,
            "positives": positives,
            "attention": attention,
        }