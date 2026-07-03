from app.domain.entities.activity import Activity


class PaceRule:

    @staticmethod
    def execute(activity: Activity):

        positives = []
        attention = []
        score = 0

        speed = activity.average_speed * 3.6

        if speed >= 10:
            positives.append("Excelente velocidade média.")
            score += 5
        else:
            attention.append("Velocidade abaixo de 10 km/h.")

        return {
            "score": score,
            "positives": positives,
            "attention": attention,
        }