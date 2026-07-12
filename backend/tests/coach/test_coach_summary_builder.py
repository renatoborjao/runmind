from app.application.coach.models.next_training import (
    NextTraining,
)
from app.application.coach.signals.coach_analysis import (
    CoachAnalysis,
)
from app.application.coach.signals.finding import (
    Finding,
    FindingSeverity,
)
from app.application.coach.summary.coach_summary_builder import (
    CoachSummaryBuilder,
)


def _finding(code: str, severity: FindingSeverity) -> Finding:

    return Finding(code=code, severity=severity, params={})


def test_positive_findings_go_to_positives_and_attention_to_improvements():

    analysis = CoachAnalysis(
        distance=_finding("DISTANCE_OK", FindingSeverity.POSITIVE),
        type_match=_finding("TYPE_MISMATCH", FindingSeverity.ATTENTION),
        intensity=_finding("INTENSITY_HIGH", FindingSeverity.POSITIVE),
        pace_effort=_finding("PACE_FAST", FindingSeverity.NEUTRAL),
        recovery=_finding("RECOVERY_SHORT", FindingSeverity.POSITIVE),
        fatigue=None,
        consistency=_finding("CONSISTENCY_GOOD", FindingSeverity.POSITIVE),
        weekly_volume=_finding("WEEKLY_VOLUME_NEAR", FindingSeverity.POSITIVE),
        next_training=NextTraining(
            day="Thursday",
            workout_type="Intervalado",
            objective="Velocidade",
            distance_km=8,
            pace="-",
            heart_rate="-",
            warmup="-",
            main_set="-",
            cooldown="-",
            shoes="-",
            notes="-",
        ),
    )

    summary = CoachSummaryBuilder.build("Renato", analysis)

    assert analysis.distance in summary.positives
    assert analysis.type_match in summary.improvements
    assert analysis.intensity in summary.positives
    assert analysis.pace_effort in summary.positives
    assert summary.history == [analysis.consistency, analysis.weekly_volume]
    assert summary.recovery == [analysis.recovery]
    assert summary.next_training is analysis.next_training
    assert summary.runner_name == "Renato"


def test_extra_workout_drops_weekly_volume_from_history():
    """Treino extra (fora do plano): o "📈 Histórico" não comenta o volume
    semanal (soava errado — "próximo de concluir" logo após corrida a mais).
    A consistência continua."""

    analysis = CoachAnalysis(
        distance=None,
        type_match=None,
        intensity=_finding("INTENSITY_MEDIUM", FindingSeverity.POSITIVE),
        pace_effort=_finding("PACE_MODERATE", FindingSeverity.NEUTRAL),
        recovery=_finding("RECOVERY_OK", FindingSeverity.POSITIVE),
        fatigue=None,
        consistency=_finding("CONSISTENCY_GOOD", FindingSeverity.POSITIVE),
        weekly_volume=_finding("WEEKLY_VOLUME_NEAR", FindingSeverity.POSITIVE),
        unplanned=_finding("UNPLANNED_WORKOUT", FindingSeverity.NEUTRAL),
        next_training=None,
    )

    summary = CoachSummaryBuilder.build("Renato", analysis)

    assert summary.history == [analysis.consistency]
    assert analysis.weekly_volume not in summary.history


def test_fatigue_finding_is_appended_to_recovery_when_present():

    analysis = CoachAnalysis(
        distance=_finding("DISTANCE_OK", FindingSeverity.POSITIVE),
        type_match=_finding("TYPE_MATCH", FindingSeverity.POSITIVE),
        intensity=_finding("INTENSITY_MEDIUM", FindingSeverity.POSITIVE),
        pace_effort=_finding("PACE_MODERATE", FindingSeverity.NEUTRAL),
        recovery=_finding("RECOVERY_LONG", FindingSeverity.ATTENTION),
        fatigue=_finding("FATIGUE_HIGH", FindingSeverity.ATTENTION),
        consistency=_finding("CONSISTENCY_LOW", FindingSeverity.ATTENTION),
        weekly_volume=_finding("WEEKLY_VOLUME_NO_GOAL", FindingSeverity.NEUTRAL),
        next_training=None,
    )

    summary = CoachSummaryBuilder.build("Renato", analysis)

    assert summary.recovery == [analysis.recovery, analysis.fatigue]
