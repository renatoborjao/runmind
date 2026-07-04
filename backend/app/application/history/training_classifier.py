from app.application.classification.training_classifier import (
    MIN_LONG_RUN_KM,
)
from app.domain.entities.activity import Activity

# Abaixo do longão, a distância só separa rodagem de regenerativo.
EASY_MIN_KM = 7.0


class TrainingClassifier:

    @staticmethod
    def classify(activity: Activity) -> str:
        """Classificação grosseira por distância, usada só no histograma
        do histórico (endpoint /history/analysis).

        A classificação real — com pace, FC e capacidade do atleta — vive
        em app.application.classification.TrainingClassifier. Aqui o longão
        segue o MESMO piso de 10km do resto do sistema; e como sem pace não
        dá pra afirmar TEMPO/VO2, distâncias médias entram como rodagem, não
        como tipos de intensidade que não conseguimos medir por distância.
        """

        distance = activity.distance / 1000

        if distance >= MIN_LONG_RUN_KM:
            return "LONG_RUN"

        if distance >= EASY_MIN_KM:
            return "EASY"

        return "RECOVERY"
