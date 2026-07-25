from app.application.coach.writer.aerobic_efficiency_writer import (
    AerobicEfficiencyWriter,
)
from app.domain.entities.aerobic_efficiency import (
    EFF_DECLINING,
    EFF_IMPROVING,
    EFF_INSUFFICIENT,
    EFF_STABLE,
    AerobicEfficiency,
)


def test_insufficient_returns_none():

    fitness = AerobicEfficiency(direction=EFF_INSUFFICIENT, runs_counted=2)

    assert AerobicEfficiencyWriter.write(fitness, "Renato") is None


def test_improving_message_has_tangible_numbers():

    fitness = AerobicEfficiency(
        direction=EFF_IMPROVING, runs_counted=8, weeks_covered=8,
        ref_hr=150, ref_pace=6.43, pace_gain_sec=8, hr_drop_bpm=7,
    )

    msg = AerobicEfficiencyWriter.write(fitness, "Renato")

    assert "evoluindo" in msg
    assert "Renato" in msg
    assert "7 bpm" in msg          # no mesmo pace, FC caiu 7 bpm
    assert "8 s/km" in msg          # na mesma FC, 8 s/km mais rápido
    assert "6:26/km" in msg         # pace de referência formatado


def test_declining_message_is_not_alarmist():

    fitness = AerobicEfficiency(
        direction=EFF_DECLINING, runs_counted=8, weeks_covered=8,
        ref_hr=150, ref_pace=6.43, pace_gain_sec=-6, hr_drop_bpm=-5,
    )

    msg = AerobicEfficiencyWriter.write(fitness, "Renato")

    assert "recuou" in msg
    assert "5 bpm mais alta" in msg
    assert "susto" in msg           # tom tranquilizador, não alarmista


def test_stable_message_is_structured_and_anchored():
    """Estável não pode soar 'jogado': tem respiro, ancora num número real
    (pace × FC de referência + nº de corridas) e fecha com ação."""

    fitness = AerobicEfficiency(
        direction=EFF_STABLE, runs_counted=8, weeks_covered=8,
        ref_hr=150, ref_pace=6.43,
    )

    msg = AerobicEfficiencyWriter.write(fitness, "Renato")

    assert "estável" in msg
    assert "Renato" in msg
    assert "\n" in msg                    # tem respiro, não é um parágrafo só
    assert "Em números" in msg
    assert "6:26/km" in msg               # pace de referência formatado
    assert "150" in msg                   # FC de referência
    assert "8 corridas" in msg            # amostra comparada
    assert "não é um problema" in msg     # tranquiliza: estável não é ruim
    assert ("tiro" in msg or "limiar" in msg)   # fechamento acionável


def test_stable_without_anchor_still_closes_with_action():
    """Sem pace/FC de referência, some o bloco 'Em números' mas a mensagem
    segue estruturada e acionável (não vira o parágrafo seco antigo)."""

    fitness = AerobicEfficiency(
        direction=EFF_STABLE, runs_counted=6, weeks_covered=7,
    )

    msg = AerobicEfficiencyWriter.write(fitness, "Renato")

    assert "estável" in msg
    assert "Em números" not in msg
    assert ("tiro" in msg or "limiar" in msg)


def test_line_compact_improving_has_number():

    fitness = AerobicEfficiency(
        direction=EFF_IMPROVING, runs_counted=8, weeks_covered=8,
        ref_hr=150, ref_pace=6.43, pace_gain_sec=8, hr_drop_bpm=7,
    )

    line = AerobicEfficiencyWriter.line(fitness)

    assert line.startswith("📈")
    assert "8 s/km" in line


def test_line_compact_none_when_insufficient():

    fitness = AerobicEfficiency(direction=EFF_INSUFFICIENT, runs_counted=1)

    assert AerobicEfficiencyWriter.line(fitness) is None


def test_improving_without_meaningful_numbers_omits_them():
    """Ganho de direção mas tradução ~0: a mensagem sai sem a linha 'Em
    números' (não mostra '0 bpm')."""

    fitness = AerobicEfficiency(
        direction=EFF_IMPROVING, runs_counted=6, weeks_covered=7,
        ref_hr=150, ref_pace=6.43, pace_gain_sec=0, hr_drop_bpm=0,
    )

    msg = AerobicEfficiencyWriter.write(fitness, "Renato")

    assert "evoluindo" in msg
    assert "Em números" not in msg
