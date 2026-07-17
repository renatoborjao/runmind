"""Previsão de tempo de prova (fórmula de Riegel): a partir do melhor
esforço real recente do atleta, estima o tempo que ele cruzaria HOJE a
distância da meta. Matemática determinística pura — sem custo de IA.

Honestidade: só prevê quando faz sentido. Sem esforço-âncora real (corrida
de verdade, ≥3km) -> None (silêncio, não invenção). Se a distância do
esforço-âncora e a da meta forem MUITO diferentes (ex.: prever maratona a
partir de um esforço de 3km), a extrapolação de Riegel é conhecidamente
pouco confiável -> corta, também None."""

from app.application.history.runner_metrics import WALK_PACE_CUTOFF
from app.application.planner.race_time_formatter import RaceTimeFormatter
from app.domain.entities.training_history import TrainingHistory
from app.domain.value_objects.sports import RUN_SPORTS

# esforço mínimo pra servir de âncora — abaixo disso é tiro/fragmento, não
# representa fundo aeróbico o suficiente pra extrapolar uma prova
MIN_ANCHOR_KM = 3.0

# expoente de fadiga do Riegel (padrão de mercado)
RIEGEL_EXPONENT = 1.06

# acima disso a extrapolação (esforço-âncora <-> meta) não é confiável
MAX_EXTRAPOLATION_RATIO = 4.0


class RaceTimePredictor:

    @staticmethod
    def predict_formatted(
        history: TrainingHistory,
        goal_distance_km: float,
        target_time: str | None,
    ) -> dict | None:
        """Previsão já formatada pra exibição + delta vs. a meta declarada
        (se houver) — usado igual pelo resumo semanal e pelo recap mensal,
        pra não duplicar a lógica de formatação/delta em cada um."""

        prediction = RaceTimePredictor.predict(history, goal_distance_km)

        if prediction is None:

            return None

        predicted_seconds = prediction["predicted_seconds"]

        target_seconds = RaceTimeFormatter.parse_hms(target_time)

        delta_seconds = (
            predicted_seconds - target_seconds
            if target_seconds is not None
            else None
        )

        return {
            "formatted": RaceTimeFormatter.format(predicted_seconds),
            "delta_seconds": delta_seconds,
            "delta_formatted": (
                RaceTimeFormatter.format(abs(delta_seconds))
                if delta_seconds is not None
                else None
            ),
        }

    @staticmethod
    def predict(
        history: TrainingHistory,
        goal_distance_km: float,
    ) -> dict | None:

        anchor = RaceTimePredictor._best_anchor(history)

        if anchor is None:

            return None

        anchor_distance_km = anchor.distance / 1000

        anchor_seconds = anchor.moving_time

        ratio = max(anchor_distance_km, goal_distance_km) / min(
            anchor_distance_km, goal_distance_km,
        )

        if ratio > MAX_EXTRAPOLATION_RATIO:

            return None

        predicted_seconds = anchor_seconds * (
            (goal_distance_km / anchor_distance_km) ** RIEGEL_EXPONENT
        )

        return {
            "predicted_seconds": predicted_seconds,
            "anchor_distance_km": round(anchor_distance_km, 2),
            "anchor_date": anchor.start_date.date().isoformat(),
        }

    @staticmethod
    def _best_anchor(history: TrainingHistory):

        candidates = [
            a for a in history.activities
            if (
                a.sport in RUN_SPORTS
                and a.distance / 1000 >= MIN_ANCHOR_KM
                and a.average_speed > 0
                and RaceTimePredictor._pace(a) <= WALK_PACE_CUTOFF
            )
        ]

        if not candidates:

            return None

        return min(candidates, key=RaceTimePredictor._pace)

    @staticmethod
    def _pace(activity) -> float:

        return (1000 / activity.average_speed) / 60
