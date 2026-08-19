"""Formata a recap da JORNADA até a prova — pensada pra ser ENCAMINHADA (abre
citando o nome, faz sentido fora de contexto) e pra dar aquele empurrão emocional
na reta final: 'olha o caminho que você fez'. Espelha o recap mensal."""

from __future__ import annotations

from app.application.coach.writer.fitness_evolution_writer import (
    FitnessEvolutionWriter,
)
from app.application.review.predicted_time_line_formatter import (
    PredictedTimeLineFormatter,
)


class RaceJourneyMessageFormatter:

    @staticmethod
    def format(runner_name: str, journey: dict) -> str:

        lines = [
            f"🏁 {runner_name}, sua jornada até a prova de {journey['race_label']}",
            "",
            "Antes de correr, olha o caminho que você já fez até aqui:",
            f"• {journey['weeks']} semanas de treino — "
            f"{journey['total_runs']} treino(s), {journey['total_km']:.1f} km "
            "no total",
            f"• Maior treino da jornada: {journey['longest_km']:.1f} km",
        ]

        predicted_line = PredictedTimeLineFormatter.line(
            journey.get("predicted_time"),
            journey.get("target_time"),
        )

        if predicted_line:

            lines.append(f"• {predicted_line}")

        fitness = journey.get("fitness")

        fitness_line = (
            FitnessEvolutionWriter.line(fitness) if fitness else None
        )

        if fitness_line:

            lines.append(f"• {fitness_line}")

        lines += [
            "",
            "Tudo isso te trouxe até aqui. O dia da prova é só COLHER o que "
            "você plantou. 🌱 Confia no processo e vai com tudo! 💪",
            "",
            "Feito com 🏃 Ritmind 💪",
        ]

        return "\n".join(lines)
