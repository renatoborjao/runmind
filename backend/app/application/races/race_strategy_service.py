"""A estratégia de prova COM o contexto real do atleta: a previsão dele (histórico ×
Garmin) e o calor previsto pro dia. O motor ([[race_strategy_engine]]) é puro; aqui ficam
as buscas (histórico já carregado, previsão do tempo na rede). Qualquer falha numa
fonte = o cartão sai sem aquela parte, nunca quebra."""

from __future__ import annotations

from app.application.coach.planning.race_strategy_engine import RaceStrategyEngine
from app.application.history.race_time_predictor import RaceTimePredictor
from app.application.races.race_heat import RaceHeat


class RaceStrategyService:

    @staticmethod
    def _prediction(history, goal, profile: str | None) -> dict | None:
        """A previsão do atleta pra distância da prova (histórico × Garmin em faixa
        quando discordam). None sem dado — o cartão então não afirma nada sobre os
        números dele."""

        try:

            if history is None or not (goal.distance_km or 0) > 0:

                return None

            return RaceTimePredictor.predict_formatted(
                history, goal.distance_km, goal.target_time, profile=profile,
            )

        except Exception as e:  # noqa: BLE001

            print(f"Estratégia de prova: previsão falhou p/ '{profile}': {e}")

            return None

    @staticmethod
    async def _context(runner, profile, goal, metrics, history):

        plan = RaceStrategyEngine.plan(goal, metrics)

        if plan is None:

            return None, None, None

        pred = RaceStrategyService._prediction(history, goal, profile)

        heat = await RaceHeat.for_race(runner, goal, history, plan.total_minutes)

        return plan, pred, heat

    @staticmethod
    async def message(runner, profile, goal, metrics, history) -> str | None:
        """O cartão completo ("como corro a prova"). None se não dá pra montar."""

        plan, pred, heat = await RaceStrategyService._context(
            runner, profile, goal, metrics, history,
        )

        if plan is None:

            return None

        return RaceStrategyEngine.build(
            runner.name, goal, metrics, profile=profile, pred=pred, heat=heat,
        )

    @staticmethod
    async def reminder(runner, profile, goal, metrics, history) -> str | None:
        """A linha curta dos toques de prova (semana, véspera, manhã)."""

        plan, pred, heat = await RaceStrategyService._context(
            runner, profile, goal, metrics, history,
        )

        if plan is None:

            return None

        return RaceStrategyEngine.reminder(goal, metrics, pred=pred, heat=heat)
