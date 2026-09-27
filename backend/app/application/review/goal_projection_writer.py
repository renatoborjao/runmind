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

# quanto dá pra ganhar por semana num ciclo (fração do tempo previsto): até
# ~0,5%/sem é realista pra amador treinando bem; até ~0,8% é ambicioso; acima
# disso a meta está além do prazo — o coach fala com franqueza
_REALISTIC_PER_WEEK = 0.005
_AMBITIOUS_PER_WEEK = 0.008


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

        gap = GoalProjectionWriter._gap_line(goal, pred, weeks_to_race)

        if gap:

            lines += ["", gap]

        if weeks_to_race is not None:

            lines += ["", f"Faltam {weeks_to_race} semanas pra prova. 🗓️"]

        return "\n".join(lines)

    @staticmethod
    def _gap_line(
        goal: TrainingGoal,
        pred: dict,
        weeks_to_race: int | None = None,
    ) -> str | None:
        """A leitura vs o tempo-alvo: já bateu, está perto, ou o que falta — e
        HONESTA sobre o tamanho do salto. Antes era sempre "Dá pra chegar"
        (8 min em 13 semanas = ~10%, bem acima do que se ganha num ciclo)."""

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

        base = (
            f"Tua meta é {target} — faltam ~*{falta}* (uns {per_km:.0f} s/km "
            "mais rápido)."
        )

        predicted = pred.get("seconds")

        if not predicted or not weeks_to_race or weeks_to_race <= 0:

            return (
                f"{base} É o que os treinos vêm construindo — consistência nas "
                "sessões-chave e recuperação em dia fazem a diferença. 💪"
            )

        needed = delta / predicted

        per_week = needed / weeks_to_race

        if per_week <= _REALISTIC_PER_WEEK:

            return (
                f"{base} No prazo que temos, é um salto realista — é manter a "
                "consistência que você chega. 💪"
            )

        if per_week <= _AMBITIOUS_PER_WEEK:

            return (
                f"{base} É ambiciosa, mas possível: pede as sessões-chave "
                "feitas E a recuperação em dia (sono) — sem isso não vem. 💪"
            )

        realistic = predicted * (1 - _REALISTIC_PER_WEEK * weeks_to_race)

        return (
            f"{base} Sendo franco: em {weeks_to_race} semanas isso é ~"
            f"{needed * 100:.0f}% mais rápido — bem acima do que se ganha num "
            "ciclo. Um alvo realista hoje seria ~*"
            f"{RaceTimeFormatter.format(realistic)}*. Dá pra manter a meta como "
            "desafio — só vale saber o tamanho do salto. Se quiser ajustar, é "
            "só me falar."
        )
