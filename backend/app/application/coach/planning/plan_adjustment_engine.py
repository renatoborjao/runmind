from app.application.coach.signals.coach_analysis import CoachAnalysis
from app.application.coach.signals.codes import DistanceStatus, FatigueLevel
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan

REDUCTION_FACTOR = 0.80


class PlanAdjustmentEngine:
    """Ajusta deterministicamente o restante do plano semanal com base
    na análise (determinística) do treino que acabou de ser executado.

    Regra (decisão de treinamento, não do LLM):
    - Treinou bem mais que o planejado E a fadiga calculada está alta
      -> reduz o volume da próxima sessão restante da semana (cutback:
      mesmo pace/tipo, menos distância, pra permitir recuperação sem
      perder o estímulo).
    - Com histórico de lesão registrado, o cutback fica mais sensível:
      fadiga moderada já basta para reduzir.
    - Qualquer outro caso (incluindo treinar bem menos) -> não mexe.
    """

    @staticmethod
    def adjust(
        plan: TrainingPlan,
        executed_session: PlannedSession,
        analysis: CoachAnalysis,
    ) -> str | None:

        # treino extra (sem sessão planejada): nada a ajustar
        if analysis.distance is None:

            return None

        if analysis.distance.code != DistanceStatus.ABOVE.value:

            return None

        if analysis.fatigue is None:

            return None

        fatigue_triggers_cutback = (
            analysis.fatigue.code == FatigueLevel.HIGH.value
            or (
                analysis.injury_risk is not None
                and analysis.fatigue.code == FatigueLevel.MODERATE.value
            )
        )

        if not fatigue_triggers_cutback:

            return None

        next_session = plan.next_session_after(
            plan.session_date(executed_session),
        )

        if next_session is None:

            return None

        delta_percent = analysis.distance.params.get(
            "delta_percent",
            0,
        )

        original_distance = next_session.planned_distance_km or 0

        next_session.planned_distance_km = round(
            original_distance * REDUCTION_FACTOR,
            1,
        )

        next_session.adjusted = True

        next_session.adjustment_reason = (
            f"Reduzido de {original_distance:.1f} km para "
            f"{next_session.planned_distance_km:.1f} km: você treinou "
            f"{delta_percent:.0f}% acima do planejado e a carga ficou "
            f"alta — ajustei o volume pra você recuperar melhor."
        )

        return next_session.adjustment_reason
