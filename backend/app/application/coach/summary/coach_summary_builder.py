from app.application.coach.models.coach_summary import (
    CoachSummary,
)
from app.application.coach.signals.coach_analysis import (
    CoachAnalysis,
)
from app.application.coach.signals.finding import (
    FindingSeverity,
)


class CoachSummaryBuilder:

    @staticmethod
    def build(
        runner_name: str,
        analysis: CoachAnalysis,
    ) -> CoachSummary:

        positives = []

        improvements = []

        # Distância e aderência ao objetivo: POSITIVE vira elogio,
        # qualquer outra severidade vira ponto de atenção. Ausentes
        # (treino em dia sem sessão planejada) são pulados.

        for finding in (analysis.distance, analysis.type_match):

            if finding is None:

                continue

            if finding.severity == FindingSeverity.POSITIVE:

                positives.append(finding)

            else:

                improvements.append(finding)

        # Treino extra entra como aviso leve.

        if analysis.unplanned is not None:

            improvements.append(analysis.unplanned)

        # Intensidade e ritmo são sempre leitura informativa do treino,
        # nunca alerta — entram direto como positives.

        positives.append(analysis.intensity)

        positives.append(analysis.pace_effort)

        history = [
            analysis.consistency,
        ]

        # Treino EXTRA (fora do plano) não fala de "progresso do volume
        # semanal": o atleta correu além/fora do planejado, então medir
        # quanto "falta pra fechar a semana" vira ruído (e soava errado —
        # "próximo de concluir" logo após uma corrida a mais). A
        # consistência continua, essa faz sentido sempre.
        if analysis.unplanned is None:

            history.append(analysis.weekly_volume)

        recovery = [
            analysis.recovery,
        ]

        if analysis.fatigue is not None:

            recovery.append(analysis.fatigue)

        if analysis.injury_risk is not None:

            recovery.append(analysis.injury_risk)

        return CoachSummary(
            runner_name=runner_name,
            positives=positives,
            improvements=improvements,
            history=history,
            recovery=recovery,
            next_training=analysis.next_training,
        )
