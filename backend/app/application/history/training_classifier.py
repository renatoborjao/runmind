from app.domain.entities.activity import Activity


class TrainingClassifier:

    @staticmethod
    def classify(activity: Activity) -> str:
        """
        Classificação inicial baseada apenas em distância.

        Essa regra será evoluída utilizando pace,
        frequência cardíaca e histórico do atleta.
        """

        distance = activity.distance / 1000

        if distance >= 14:
            return "LONG_RUN"

        if distance >= 10:
            return "TEMPO"

        if distance >= 7:
            return "EASY"

        return "RECOVERY"