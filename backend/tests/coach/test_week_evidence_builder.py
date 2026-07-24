from datetime import date
from unittest.mock import MagicMock, patch

from app.application.coach.memory.week_evidence_builder import (
    WeekEvidenceBuilder,
)
from app.domain.entities.adherence_report import (
    ADHERENCE_FALLING,
    ADHERENCE_INSUFFICIENT,
    AdherenceReport,
    MissedPattern,
    WeekAdherence,
)
from app.domain.entities.body_reading import BodyReading, RecoveryTrend
from app.domain.entities.training_load import TrainingLoad

MOD = "app.application.coach.memory.week_evidence_builder"


def _history():

    h = MagicMock()
    h.activities = []

    return h


def _report(**over) -> AdherenceReport:

    defaults = dict(
        weeks=[
            WeekAdherence(week_start=date(2026, 7, 6), planned=3, done=2),
            WeekAdherence(week_start=date(2026, 7, 13), planned=3, done=1),
        ],
        rate=0.5,
        trend=ADHERENCE_FALLING,
        missed_day=MissedPattern(label="Sunday", count=2, opportunities=2),
        missed_type=None,
    )

    defaults.update(over)

    return AdherenceReport(**defaults)


def _body(has_data=True) -> BodyReading:

    load = TrainingLoad(
        acute_load=300.0,
        chronic_load=200.0,
        acwr=1.5,
        status="HIGH",
        days_of_history=40,
    )

    recovery = RecoveryTrend(
        hrv_recent=45.0,
        hrv_direction="falling",
        short_nights=4,
        nights_counted=7,
        days_covered=7 if has_data else 0,
    )

    return BodyReading(
        load=load,
        recovery=recovery,
        body_state="STRAINED",
        limiter="sono",
    )


def _build(executed="", report=None, body=None, signals=None, life=""):

    report = report or _report()
    body = body if body is not None else _body()
    signals = signals or []

    with patch(f"{MOD}.WeeklyPlanRepository") as repo_cls, patch(
        f"{MOD}.ExecutedWeekSummary"
    ) as execs, patch(f"{MOD}.AdherenceAnalyzer") as adh, patch(
        f"{MOD}.BodyReadingBuilder"
    ) as brb, patch(
        f"{MOD}.CoachingSignalRecorder"
    ) as rec, patch(
        f"{MOD}.RunnerMemoryService"
    ) as mem, patch(
        f"{MOD}.today_local", return_value=date(2026, 7, 19)
    ):

        # semana FECHADA: domingo (13+6=19/07) <= hoje (19/07)
        plan = MagicMock()
        plan.week_start = date(2026, 7, 13)
        repo_cls.return_value.history.return_value = [plan]
        execs.build.return_value = executed
        adh.analyze.return_value = report
        brb.build.return_value = body
        rec.load.return_value = signals
        mem.render.return_value = life

        return WeekEvidenceBuilder.build("renato", _history())


def test_stitches_all_sources():

    evidence = _build(
        executed="Treinos realizados: - Ter 8km",
        signals=[{"kind": "aceitou_move", "detail": "moveu longão"}],
    )

    assert "Treinos realizados: - Ter 8km" in evidence
    assert "tendência FALLING" in evidence
    assert "Mais fura no dia domingo" in evidence
    assert "aceitou_move: moveu longão" in evidence
    assert "estado STRAINED" in evidence
    assert "limitador: sono" in evidence
    assert "ACWR 1.50" in evidence


def test_life_context_is_included_when_present():

    evidence = _build(life="- [disponibilidade] Viagem a trabalho (18/07)")

    assert "Contexto de vida" in evidence
    assert "Viagem a trabalho" in evidence
    assert "NÃO vire padrão" in evidence


def test_body_skipped_without_garmin_data():

    evidence = _build(body=_body(has_data=False))

    assert "STRAINED" not in evidence
    # o resto ainda entra
    assert "tendência FALLING" in evidence


def test_empty_when_nothing_to_learn():

    empty_report = AdherenceReport(
        weeks=[], rate=None, trend=ADHERENCE_INSUFFICIENT,
    )

    evidence = _build(
        executed="",
        report=empty_report,
        body=_body(has_data=False),
        signals=[],
    )

    assert evidence == ""
