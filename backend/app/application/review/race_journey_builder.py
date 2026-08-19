"""Monta os números da JORNADA do atleta até a prova — o "olha o caminho que
você fez" que sai nos dias que antecedem a prova (companheiro de prova). É o
retrospecto emocional: quantas semanas, quantos km e treinos, o maior treino, a
evolução de forma e a projeção pro dia. Reaproveita as mesmas peças do recap
mensal (evolução + previsão de prova), mas na janela da JORNADA INTEIRA (do 1º
treino conosco até hoje), não do mês. Ver [[MonthlyRecapBuilder]]."""

from __future__ import annotations

from app.application.coach.intelligence.fitness_reading_service import (
    FitnessReadingService,
)
from app.application.history.race_time_predictor import RaceTimePredictor
from app.application.history.weekly_buckets import activity_date
from app.core.clock import today_local
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_history import TrainingHistory


class RaceJourneyBuilder:

    @staticmethod
    def build(
        runner: RunnerProfile,
        history: TrainingHistory,
        goal: TrainingGoal,
    ) -> dict | None:
        """Números da jornada até a prova, ou None se não há treino no histórico
        (nada a recapitular) ou não há prova de verdade no horizonte."""

        activities = history.activities

        if not activities or goal.race_date is None:

            return None

        total_km = sum(a.distance for a in activities) / 1000

        longest_km = max(a.distance for a in activities) / 1000

        dates = [activity_date(a) for a in activities]

        weeks = max(1, (today_local() - min(dates)).days // 7)

        # dias distintos treinados / semanas ≈ ritmo de treino da jornada
        days_trained = len(set(dates))

        return {
            "race_label": goal.race_label,
            "weeks": weeks,
            "total_km": round(total_km, 1),
            "total_runs": len(activities),
            "days_trained": days_trained,
            "longest_km": round(longest_km, 1),
            "target_time": goal.target_time,
            "predicted_time": RaceJourneyBuilder._predicted(goal, history),
            "fitness": RaceJourneyBuilder._fitness(runner.id),
        }

    @staticmethod
    def _predicted(goal: TrainingGoal, history: TrainingHistory) -> dict | None:
        """Previsão de tempo pra prova (forma atual × distância-alvo). Só quando
        há prova de verdade — que é o caso aqui (build já exigiu race_date)."""

        try:

            if not goal.distance_km:

                return None

            return RaceTimePredictor.predict_formatted(
                history, goal.distance_km, goal.target_time,
            )

        except Exception as e:

            print(f"Jornada: previsão indisponível: {e}")

            return None

    @staticmethod
    def _fitness(profile: str):
        """Veredito de evolução de forma na data de hoje. Best-effort."""

        try:

            return FitnessReadingService.read_evolution(profile)

        except Exception as e:

            print(f"Jornada: evolução indisponível p/ '{profile}': {e}")

            return None
