from datetime import date, timedelta

from app.application.history.acute_strain_analyzer import AcuteStrainAnalyzer
from app.domain.entities.daily_health import DailyHealth

START = date(2026, 7, 20)


def _series(rows: list[tuple[int, int]]) -> list[DailyHealth]:
    """rows = [(resting_hr, hrv_last_night)] em ordem cronológica."""

    return [
        DailyHealth(
            date=(START + timedelta(days=i)).isoformat(),
            resting_hr=rhr,
            hrv_last_night=hrv,
        )
        for i, (rhr, hrv) in enumerate(rows)
    ]


def _baseline(rhr=55, hrv=60, days=21):

    return [(rhr, hrv)] * days


def test_strain_fires_on_rhr_up_and_hrv_down():
    """O padrão agudo: FC-repouso salta E HRV cai vs a base -> alerta."""

    series = _series(_baseline() + [(62, 52), (63, 51)])  # +7 bpm, -~14% HRV

    v = AcuteStrainAnalyzer.detect(series)

    assert v.is_strained
    assert v.rhr_recent > v.rhr_baseline
    assert v.hrv_recent < v.hrv_baseline


def test_no_strain_when_only_rhr_up():
    """FC subiu mas HRV firme -> não é o padrão (pode ser só uma noite ruim)."""

    series = _series(_baseline() + [(63, 60), (63, 61)])

    assert not AcuteStrainAnalyzer.detect(series).is_strained


def test_no_strain_when_only_hrv_down():

    series = _series(_baseline() + [(55, 51), (55, 50)])

    assert not AcuteStrainAnalyzer.detect(series).is_strained


def test_no_strain_when_stable():

    series = _series(_baseline() + [(55, 60), (56, 59)])

    assert not AcuteStrainAnalyzer.detect(series).is_strained


def test_no_strain_without_enough_baseline():

    series = _series([(55, 60), (55, 60), (62, 52), (63, 51)])

    assert not AcuteStrainAnalyzer.detect(series).is_strained


def test_renato_gripe_case_does_not_fire():
    """Honestidade: a gripe real do Renato NÃO deu sinal (HRV ficou alto, FC
    estável) — o detector corretamente NÃO dispara nesse caso."""

    # base ~56/60; nos dias da gripe FC 56/59 e HRV 66/61 (sem queda)
    series = _series(_baseline(rhr=56, hrv=60) + [(56, 66), (59, 61)])

    assert not AcuteStrainAnalyzer.detect(series).is_strained
