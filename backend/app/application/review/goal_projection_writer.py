"""'Rumo à meta' — a projeção que dá NORTE: no nível atual, quanto sairia a
distância da meta do atleta, o quanto falta pro tempo-alvo e se está no caminho.

Reusa o [[RaceTimePredictor]] (Riegel do melhor esforço real) e VALE mesmo SEM
data de prova — um objetivo de distância (10k, 21k) sem competição também merece
saber se está no rumo. Determinístico (a matemática do tempo é exata). None
quando não há distância-meta ou não há esforço-âncora pra prever (silêncio, não
invenção). Ver [[project_modelo_pace_vdot]] e [[project_multiplos_objetivos]]."""

from app.application.history.race_time_predictor import RaceTimePredictor
from app.application.planner.race_time_formatter import RaceTimeFormatter
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_history import TrainingHistory

# folga (s) pra considerar que já "bateu" a meta — dentro disso é empate técnico
_ON_TARGET_SLACK = 20


class GoalProjectionWriter:

    @staticmethod
    def write(
        runner_name: str,
        goal: TrainingGoal,
        history: TrainingHistory,
        weeks_to_race: int | None = None,
    ) -> str | None:
        """Bloco 'rumo à meta' pro atleta, ou None se não dá pra projetar."""

        distance = goal.distance_km or 0.0

        if distance <= 0:

            return None

        pred = RaceTimePredictor.predict_formatted(
            history, distance, goal.target_time,
        )

        if pred is None:

            return None

        label = goal.race_label or f"{distance:.0f} km"

        lines = [
            f"🎯 Rumo à sua meta ({label})",
            "",
            f"No teu nível atual, teu tempo seria ~*{pred['formatted']}*.",
        ]

        gap = GoalProjectionWriter._gap_line(goal, pred)

        if gap:

            lines += ["", gap]

        if weeks_to_race is not None:

            lines += ["", f"Faltam {weeks_to_race} semanas pra prova. 🗓️"]

        return "\n".join(lines)

    @staticmethod
    def _gap_line(goal: TrainingGoal, pred: dict) -> str | None:
        """A leitura vs o tempo-alvo: já bateu, está perto, ou o que falta."""

        delta = pred.get("delta_seconds")

        if delta is None:  # sem tempo-alvo declarado

            return None

        target = goal.target_time

        # delta = previsto − alvo. Negativo = já mais rápido que a meta.
        if delta <= _ON_TARGET_SLACK:

            return (
                f"E olha só: você JÁ está no ritmo da tua meta de {target} — "
                "dá pra buscar até um pouco mais. 🚀"
            )

        falta = RaceTimeFormatter.format(delta)

        per_km = delta / goal.distance_km

        return (
            f"Tua meta é {target} — faltam ~*{falta}* (uns "
            f"{per_km:.0f} s/km mais rápido). Dá pra chegar; é isso que os "
            "treinos vêm construindo. 💪"
        )
