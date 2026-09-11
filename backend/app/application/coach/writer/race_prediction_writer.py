"""Narra a previsão de prova do Garmin (5K/10K/meia/maratona) numa linha
athlete-facing. Determinístico — os tempos vêm prontos da entidade. Texto puro
(canal sem negrito): hierarquia por emoji/rótulo, estilo da casa."""

from app.domain.entities.race_prediction import RacePrediction


class RacePredictionWriter:

    @staticmethod
    def block(prediction: RacePrediction | None) -> str | None:
        """Bloco 'projeção do Garmin' — None quando não há nenhuma distância
        prevista (o chamador simplesmente omite)."""

        if prediction is None or not prediction.has_data:

            return None

        parts = [
            (f"5K {prediction.time_5k}", prediction.time_5k),
            (f"10K {prediction.time_10k}", prediction.time_10k),
            (f"21K {prediction.time_half}", prediction.time_half),
            (f"42K {prediction.time_marathon}", prediction.time_marathon),
        ]

        line = " · ".join(label for label, value in parts if value)

        return "\n".join(
            [
                "🏁 Projeção do teu Garmin (capacidade de hoje):",
                line,
                "É o tempo que teu motor entrega AGORA — a meta fica visível. 👊",
            ]
        )

    @staticmethod
    def line(prediction: RacePrediction | None) -> str | None:
        """Uma linha compacta (pro plano/contexto reusar): '10K ~51:26 (Garmin)'.
        Prioriza o 10K (distância-alvo mais comum); cai pro 5K se faltar."""

        if prediction is None or not prediction.has_data:

            return None

        if prediction.time_10k:

            return f"10K ~{prediction.time_10k} (Garmin)"

        if prediction.time_5k:

            return f"5K ~{prediction.time_5k} (Garmin)"

        return None
