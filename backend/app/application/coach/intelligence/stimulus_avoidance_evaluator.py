"""Avalia se UM treino de qualidade foi 'evitado' pelo atleta — rebaixou o
tipo (planejou tiro/ritmo, fez leve) OU furou o pace (fez o tipo certo, mas
bem mais devagar que o alvo). É a peça pura, por-treino, do detector proativo
de aversão: aqui NÃO se muda nada, só se classifica o treino."""

from app.domain.entities.enriched_activity import EnrichedActivity
from app.domain.entities.planned_session import PlannedSession

# Famílias de estímulo de qualidade — o padrão de fuga é por FAMÍLIA: quem
# foge de tiro foge de VO2/intervalado/fartlek; quem foge de ritmo foge de
# tempo/limiar. Rodagem, longão e regenerativo não têm estímulo a "evitar".
_SPEED = {"VO2", "INTERVAL", "FARTLEK"}

_TEMPO = {"TEMPO", "THRESHOLD", "PROGRESSION"}

# Rebaixou = executou como treino leve (fugiu do estímulo prescrito).
_EASY_EXECUTED = {"EASY", "RODAGEM", "RECOVERY", "WALK", "RUN_WALK"}

# "Furou o pace" só onde o pace MÉDIO do treino é comparável ao alvo: esforço
# contínuo (tempo/limiar). Em tiro/fartlek/progressivo a média inclui
# aquecimento/recuperação e sairia sempre "lenta" (falso positivo) — ali vale
# só o rebaixamento de tipo.
_PACE_CHECK = {"TEMPO", "THRESHOLD"}

# Quanto mais devagar que o teto do alvo já conta como "furou" (min/km).
_PACE_MISS_MARGIN = 0.5


class StimulusAvoidanceEvaluator:

    @staticmethod
    def evaluate(
        planned: PlannedSession | None,
        executed: EnrichedActivity,
    ) -> tuple[str, bool] | None:
        """(família, evitou) ou None quando não é treino de qualidade
        (rodagem/longão/regenerativo/run-walk/extra sem plano)."""

        if planned is None:

            return None

        family = StimulusAvoidanceEvaluator._family(planned.workout_type)

        if family is None:

            return None

        avoided = (
            StimulusAvoidanceEvaluator._downgraded(executed)
            or StimulusAvoidanceEvaluator._pace_missed(planned, executed)
        )

        return family, avoided

    @staticmethod
    def _family(workout_type: str) -> str | None:

        if workout_type in _SPEED:

            return "SPEED"

        if workout_type in _TEMPO:

            return "TEMPO"

        return None

    @staticmethod
    def _downgraded(executed: EnrichedActivity) -> bool:

        return executed.training_type in _EASY_EXECUTED

    @staticmethod
    def _pace_missed(
        planned: PlannedSession,
        executed: EnrichedActivity,
    ) -> bool:

        if planned.workout_type not in _PACE_CHECK:

            return False

        target = StimulusAvoidanceEvaluator._pace_to_minutes(
            planned.target_pace_max,
        )

        if target is None or not executed.pace_min_km:

            return False

        return executed.pace_min_km > target + _PACE_MISS_MARGIN

    @staticmethod
    def _pace_to_minutes(value: str | None) -> float | None:
        """'5:30' -> 5.5 min/km. Formato inválido/ausente -> None."""

        if not value or ":" not in value:

            return None

        try:

            minutes, seconds = value.split(":")

            return int(minutes) + int(seconds) / 60

        except (ValueError, TypeError):

            return None
