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
from app.domain.entities.aerobic_efficiency import (
    EFF_IMPROVING,
    AerobicEfficiency,
)
from app.domain.entities.body_reading import BodyReading, RecoveryTrend
from app.domain.entities.daily_checkin import DailyCheckin
from app.domain.entities.fitness_evolution import (
    EVO_CLEAR,
    EVO_IMPROVING,
    FitnessEvolution,
)
from app.domain.entities.session_rpe import SessionRpe
from app.domain.entities.signal_trend import (
    CONF_CLEAR,
    TREND_IMPROVING,
    SignalTrend,
)
from app.domain.entities.training_load import TrainingLoad

MOD = "app.application.coach.memory.week_evidence_builder"


# --- qualidade de execução por tipo (o aprofundamento da memória) ---

from types import SimpleNamespace  # noqa: E402


def _act(pace_min_km: float):
    """Activity com pace médio = pace_min_km (min/km)."""

    speed = 1000 / (pace_min_km * 60)  # m/s

    return SimpleNamespace(average_speed=speed)


def test_pace_vs_target_on_target_slower_faster():

    session = SimpleNamespace(target_pace_min="5:00", target_pace_max="5:10")

    assert WeekEvidenceBuilder._pace_vs_target(session, _act(5.083)) == "no alvo"

    slower = WeekEvidenceBuilder._pace_vs_target(session, _act(5.42))
    assert "LENTO" in slower and "15s/km" in slower

    faster = WeekEvidenceBuilder._pace_vs_target(session, _act(4.83))
    assert "rápido" in faster


def test_is_structured_detects_repeats():

    structured = SimpleNamespace(
        steps=[SimpleNamespace(is_repeat=True, kind="repeat")],
        workout_type="Tiros",
    )
    continuous = SimpleNamespace(
        steps=[SimpleNamespace(is_repeat=False, kind="run")],
        workout_type="Rodagem Leve",
    )

    assert WeekEvidenceBuilder._is_structured(structured) is True
    assert WeekEvidenceBuilder._is_structured(continuous) is False


def test_is_structured_detects_by_type_name_without_steps():
    """'Intervalado de Limiar' sem passos gravados ainda é estruturado — não
    pode cair no pace médio (que engana num treino de tiros)."""

    session = SimpleNamespace(steps=[], workout_type="Intervalado de Limiar")

    assert WeekEvidenceBuilder._is_structured(session) is True


def test_quality_line_skips_structured_when_no_block_data():
    """Estruturado SEM comparação bloco-a-bloco -> "" (não chuta por pace)."""

    session = SimpleNamespace(
        target_pace_min="5:25", target_pace_max="5:30",
        steps=[], workout_type="Intervalado de Limiar",
    )

    with patch(f"{MOD}.PlannedExecutionMatcher.match", return_value=None):

        assert WeekEvidenceBuilder._quality_line(session, _act(6.0)) == ""


def test_quality_line_uses_block_comparison_for_structured():

    session = SimpleNamespace(
        target_pace_min="5:25", target_pace_max="5:30",
        steps=[SimpleNamespace(is_repeat=True, kind="repeat")],
    )

    comparison = SimpleNamespace(
        blocks=[
            SimpleNamespace(within_target=True),
            SimpleNamespace(within_target=True),
            SimpleNamespace(within_target=False),
        ],
        missing=[],
    )

    with patch(f"{MOD}.PlannedExecutionMatcher.match", return_value=comparison):

        line = WeekEvidenceBuilder._quality_line(session, _act(5.3))

    assert line == "2/3 blocos no alvo"


def test_quality_line_falls_back_to_pace_for_continuous():

    session = SimpleNamespace(
        target_pace_min="6:00", target_pace_max="6:10",
        steps=[SimpleNamespace(is_repeat=False, kind="run")],
    )

    # sem estrutura pra bloco (match None) -> pace-vs-alvo do contínuo
    with patch(f"{MOD}.PlannedExecutionMatcher.match", return_value=None):

        line = WeekEvidenceBuilder._quality_line(session, _act(6.05))

    assert line == "no alvo"


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


def _evo(**over) -> FitnessEvolution:
    """Veredito de evolução com lastro e fresco (não stale)."""

    defaults = dict(
        direction=EVO_IMPROVING,
        confidence=EVO_CLEAR,
        ef=AerobicEfficiency(
            direction=EFF_IMPROVING,
            runs_counted=6,
            pace_gain_sec=17,
        ),
        days_since_last_run=2,
    )

    defaults.update(over)

    return FitnessEvolution(**defaults)


def _trend(direction=TREND_IMPROVING) -> SignalTrend:

    return SignalTrend(
        direction=direction,
        confidence=CONF_CLEAR,
        points=8,
        span_days=40,
        span_weeks=6,
        relative_change=0.03,
        per_week=0.1,
        r_squared=0.6,
        recent_value=52.0,
        earlier_value=50.0,
        mean_value=51.0,
    )


def _build(
    executed="",
    report=None,
    body=None,
    signals=None,
    life="",
    evolution=None,
    srpe=None,
    checkins=None,
):

    report = report or _report()
    body = body if body is not None else _body()
    signals = signals or []
    # por padrão, evolução INSUFICIENTE e sem subjetivo — as novas seções só
    # entram nos testes que as fornecem
    evolution = evolution if evolution is not None else FitnessEvolution()
    srpe = srpe or []
    checkins = checkins or []

    with patch(f"{MOD}.WeeklyPlanRepository") as repo_cls, patch(
        f"{MOD}.ExecutedWeekSummary"
    ) as execs, patch(f"{MOD}.AdherenceAnalyzer") as adh, patch(
        f"{MOD}.BodyReadingService"
    ) as brs, patch(
        f"{MOD}.CoachingSignalRecorder"
    ) as rec, patch(
        f"{MOD}.RunnerMemoryService"
    ) as mem, patch(
        f"{MOD}.FitnessReadingService"
    ) as fit, patch(
        f"{MOD}.SessionRpeRepository"
    ) as srpe_cls, patch(
        f"{MOD}.CheckinRepository"
    ) as chk_cls, patch(
        f"{MOD}.today_local", return_value=date(2026, 7, 19)
    ):

        # semana FECHADA: domingo (13+6=19/07) <= hoje (19/07)
        plan = MagicMock()
        plan.week_start = date(2026, 7, 13)
        repo_cls.return_value.history.return_value = [plan]
        execs.build.return_value = executed
        adh.analyze.return_value = report
        # o service devolve (leitura, trajetória); a trajetória sem fato não
        # muda o texto (a recorrência é testada à parte no analisador)
        brs.read.return_value = (body, MagicMock(fact=""))
        rec.load.return_value = signals
        mem.render.return_value = life
        fit.read_evolution.return_value = evolution
        srpe_cls.return_value.load_sessions.return_value = srpe
        chk_cls.return_value.load.return_value = checkins

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


def test_evolution_included_with_tangible_gain_and_signals():

    evidence = _build(
        evolution=_evo(
            quality=_trend(),
            vo2max=_trend(),
        ),
    )

    assert "está evoluindo?" in evidence
    assert "IMPROVING (CLEAR)" in evidence
    assert "17 s/km" in evidence
    assert "6 corridas" in evidence
    assert "em ritmo forte: IMPROVING" in evidence
    assert "VO₂máx da Garmin: IMPROVING" in evidence


def test_evolution_capped_gain_is_phrased_as_more_than():

    evidence = _build(
        evolution=_evo(
            ef=AerobicEfficiency(
                direction=EFF_IMPROVING,
                runs_counted=5,
                pace_gain_sec=40,
                pace_gain_capped=True,
            ),
        ),
    )

    assert "mais de 40 s/km" in evidence


def test_evolution_skipped_when_insufficient_or_stale():

    # insuficiente (default) não entra
    assert "está evoluindo?" not in _build()

    # com lastro mas VELHO (stale) também não — forma velha não é a de agora
    stale = _evo(days_since_last_run=30)
    assert "está evoluindo?" not in _build(evolution=stale)


def test_subjective_srpe_and_checkin_of_the_closed_week():

    evidence = _build(
        srpe=[
            # 16/07 = quinta (dentro da semana 13-19/07)
            SessionRpe(
                activity_id=1,
                day="2026-07-16",
                duration_min=50.0,
                rpe=8,
                srpe=400.0,
                at="2026-07-16T19:00:00-03:00",
            ),
            # 05/07 = fora da semana fechada, NÃO entra
            SessionRpe(
                activity_id=2,
                day="2026-07-05",
                duration_min=40.0,
                rpe=5,
                srpe=200.0,
                at="2026-07-05T19:00:00-03:00",
            ),
        ],
        checkins=[
            DailyCheckin(
                day="2026-07-15",
                at="2026-07-15T08:00:00-03:00",
                energy=2,
                sleep_quality=1,
                note="acordei detonado",
            ),
        ],
    )

    assert "Como ELE sentiu a semana" in evidence
    assert "quinta-feira: esforço percebido RPE 8/10 (sRPE 400)" in evidence
    assert "sRPE 200" not in evidence          # fora da semana fechada
    assert "energia 2/5" in evidence
    assert "sono 1/5" in evidence
    assert "acordei detonado" in evidence


def test_subjective_skipped_when_no_reports():

    assert "sentiu a semana" not in _build(srpe=[], checkins=[])
