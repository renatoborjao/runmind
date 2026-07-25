from app.application.coach.writer.fitness_evolution_writer import (
    FitnessEvolutionWriter,
)
from app.domain.entities.aerobic_efficiency import (
    EFF_IMPROVING,
    EFF_STABLE,
    AerobicEfficiency,
)
from app.domain.entities.fitness_evolution import (
    EVO_IMPROVING,
    EVO_INSUFFICIENT,
    EVO_STABLE,
    FitnessEvolution,
)
from app.domain.entities.signal_trend import (
    CONF_CLEAR,
    TREND_IMPROVING,
    SignalTrend,
)


def _ef(direction=EFF_STABLE, **kw):

    return AerobicEfficiency(
        direction=direction, runs_counted=8, weeks_covered=8,
        ref_hr=150, ref_pace=6.43, **kw,
    )


def _vo2(direction=TREND_IMPROVING):

    return SignalTrend(
        direction=direction, confidence=CONF_CLEAR, points=8, span_days=40,
        span_weeks=6, relative_change=0.05, per_week=0.1, r_squared=0.6,
        recent_value=45.2, earlier_value=43.1, mean_value=44.0,
    )


def test_insufficient_returns_none():

    evo = FitnessEvolution(direction=EVO_INSUFFICIENT)

    assert FitnessEvolutionWriter.write(evo, "Renato") is None


def test_stable_ef_only_is_structured_and_flags_pending():
    """Só EF (saúde recém-conectada): mensagem estruturada, mostra o EF e
    deixa claro que VO₂máx/FC-repouso ainda estão juntando histórico."""

    evo = FitnessEvolution(direction=EVO_STABLE, ef=_ef())

    msg = FitnessEvolutionWriter.write(evo, "Renato")

    assert "estável" in msg
    assert "Renato" in msg
    assert "Por que essa leitura" in msg
    assert "Eficiência aeróbica" in msg
    assert "juntando histórico" in msg        # nota de pendência
    assert ("tiro" in msg or "limiar" in msg)  # fecho acionável


def test_improving_with_vo2max_shows_both_signals():

    evo = FitnessEvolution(
        direction=EVO_IMPROVING,
        confidence=CONF_CLEAR,
        ef=_ef(direction=EFF_IMPROVING, pace_gain_sec=8, hr_drop_bpm=7),
        vo2max=_vo2(),
    )

    msg = FitnessEvolutionWriter.write(evo, "Renato")

    assert "evoluindo" in msg
    assert "VO₂máx (Garmin): subindo" in msg
    assert "de 43.1 pra 45.2" in msg          # range do VO₂máx
    assert "8 s/km" in msg                     # tradução tangível do EF
    assert "VO₂máx" not in _pending_part(msg)  # já entrou, não fica pendente


def test_line_delegates_to_ef():

    evo = FitnessEvolution(direction=EVO_IMPROVING, ef=_ef(
        direction=EFF_IMPROVING, pace_gain_sec=8, hr_drop_bpm=7,
    ))

    line = FitnessEvolutionWriter.line(evo)

    assert line.startswith("📈")


def test_line_none_without_ef():

    assert FitnessEvolutionWriter.line(FitnessEvolution()) is None


def _pending_part(msg: str) -> str:
    """Trecho da linha de pendência (entre parênteses), pra checar que um sinal
    presente NÃO aparece como pendente."""

    for line in msg.splitlines():

        if "juntando histórico" in line:

            return line

    return ""
