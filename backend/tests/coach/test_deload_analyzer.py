from app.application.history.deload_analyzer import (
    DeloadAnalyzer,
    deload_chat_line,
    deload_directive,
)
from app.domain.entities.body_reading import FALLING, STABLE, RecoveryTrend


def _recovery(hrv=STABLE, rhr=STABLE) -> RecoveryTrend:

    return RecoveryTrend(
        hrv_direction=hrv,
        rhr_direction=rhr,
        days_covered=7,
    )


def test_due_after_three_building_weeks():

    d = DeloadAnalyzer.assess([80, 90, 100], _recovery())

    assert d.due is True
    assert d.building_weeks == 3
    assert deload_directive(d).startswith("SEMANA DE DESCARGA")


def test_not_due_with_short_block():

    d = DeloadAnalyzer.assess([80, 90], _recovery())

    assert d.due is False
    assert deload_directive(d) == ""
    assert deload_chat_line(d) == ""


def test_recovery_week_resets_the_block():
    """Um recuo no meio (semana leve) reinicia a contagem — logo após uma
    descarga o bloco recomeça do zero."""

    d = DeloadAnalyzer.assess([100, 110, 50, 120], _recovery())

    assert d.building_weeks == 1
    assert d.due is False


def test_fatigue_brings_deload_sooner():
    """Recuperação caindo antecipa a descarga pra 2 semanas de bloco."""

    d = DeloadAnalyzer.assess([90, 100], _recovery(hrv=FALLING))

    assert d.due is True
    assert "recuperação caindo" in d.reason


def test_taper_zone_disables_deload():
    """Perto da prova o taper cuida do recuo — não empilha descarga de bloco."""

    d = DeloadAnalyzer.assess([80, 90, 100, 110], _recovery(), weeks_to_race=2)

    assert d.due is False


def test_zeros_reset_streak():

    d = DeloadAnalyzer.assess([0, 0, 60, 70], _recovery())

    assert d.building_weeks == 2
    assert d.due is False


def test_low_acwr_blocks_deload_even_with_fatigue_signal():
    """Bug do Maurício: ACWR 0.97 (carga aguda <= crônica) + rhr caindo não
    justifica descarga — sem sobrecarga, semana leve à força só destreina."""

    d = DeloadAnalyzer.assess(
        [294, 151, 344, 252], _recovery(rhr=FALLING), acwr=0.97
    )

    assert d.due is False
    assert "carga não está elevada" in d.reason
    assert deload_directive(d) == ""


def test_elevated_acwr_still_allows_deload():
    """Com carga elevada de verdade (ACWR alto), a descarga do bloco vale."""

    d = DeloadAnalyzer.assess([80, 90, 100], _recovery(), acwr=1.25)

    assert d.due is True
    assert d.building_weeks == 3


def test_acwr_none_keeps_legacy_behavior():
    """Sem dado de ACWR, o gatilho segue pelo bloco (retrocompat)."""

    d = DeloadAnalyzer.assess([80, 90, 100], _recovery(), acwr=None)

    assert d.due is True
